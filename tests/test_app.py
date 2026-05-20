import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from config_manager import load_config, save_config
from gallery_store import GalleryStore
from preview import (
    fit_image_size,
    format_file_size,
    get_preview_url,
    image_file_to_dib_bytes,
    render_annotations,
)
from server import create_app


class ConfigTests(unittest.TestCase):
    def test_load_config_merges_old_shape_with_new_defaults(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "hotkey": "ctrl+alt+9",
                        "port": 8892,
                        "save_directory": "shots",
                    }
                ),
                encoding="utf-8",
            )

            config = load_config(config_path)

        self.assertEqual(config["hotkey"], "ctrl+alt+9")
        self.assertEqual(config["port"], 8892)
        self.assertEqual(config["save_directory"], "shots")
        self.assertEqual(config["database_path"], "gallery.sqlite3")
        self.assertEqual(
            config["sharing"], {"lan_enabled": False, "copy_after_capture": "local"}
        )


class GalleryStoreTests(unittest.TestCase):
    def test_share_tokens_are_created_and_revoked(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "capture.png"
            Image.new("RGB", (8, 6), "#ffffff").save(image_path)
            store = GalleryStore(root / "gallery.sqlite3")

            capture = store.add_capture("capture.png", image_path, 8, 6, image_path.stat().st_size)
            shared = store.set_share_enabled(capture["id"], True)

            self.assertTrue(shared["share_enabled"])
            self.assertIsNotNone(shared["share_token"])
            self.assertEqual(store.get_by_token(shared["share_token"])["id"], capture["id"])

            unshared = store.set_share_enabled(capture["id"], False)
            self.assertFalse(unshared["share_enabled"])
            self.assertIsNone(unshared["share_token"])
            self.assertIsNone(store.get_by_token(shared["share_token"]))


class PreviewTests(unittest.TestCase):
    def test_format_file_size_uses_readable_units(self):
        self.assertEqual(format_file_size(512), "512 B")
        self.assertEqual(format_file_size(1536), "1.5 KB")
        self.assertEqual(format_file_size(2 * 1024 * 1024), "2.0 MB")

    def test_fit_image_size_preserves_aspect_ratio(self):
        self.assertEqual(fit_image_size((1600, 900), (800, 800)), (800, 450))
        self.assertEqual(fit_image_size((900, 1600), (800, 800)), (450, 800))

    def test_get_preview_url_prefers_lan_url_when_available(self):
        self.assertEqual(
            get_preview_url({"local_url": "http://127.0.0.1/image", "lan_url": "http://lan/image"}),
            "http://lan/image",
        )
        self.assertEqual(
            get_preview_url({"local_url": "http://127.0.0.1/image", "lan_url": None}),
            "http://127.0.0.1/image",
        )

    def test_image_file_to_dib_bytes_removes_bmp_file_header(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "capture.png"
            Image.new("RGB", (8, 6), "#ffffff").save(image_path)

            dib_bytes = image_file_to_dib_bytes(image_path)

        self.assertNotEqual(dib_bytes[:2], b"BM")
        self.assertEqual(int.from_bytes(dib_bytes[:4], "little"), 40)

    def test_render_annotations_draws_on_image(self):
        image = Image.new("RGB", (40, 40), "#ffffff")
        annotated = render_annotations(
            image,
            [
                {
                    "tool": "rectangle",
                    "color": "#ef4444",
                    "width": 4,
                    "start": (5, 5),
                    "end": (25, 25),
                }
            ],
        )

        self.assertNotEqual(annotated.getpixel((5, 5)), (255, 255, 255))


class ServerTests(unittest.TestCase):
    def make_app(self, lan_enabled=False):
        temp_dir = tempfile.TemporaryDirectory()
        root = Path(temp_dir.name)
        screenshots = root / "screenshots"
        screenshots.mkdir()
        config_path = root / "config.json"
        config = {
            "hotkey": "ctrl+alt+9",
            "port": 8892,
            "save_directory": str(screenshots),
            "database_path": str(root / "gallery.sqlite3"),
            "sharing": {
                "lan_enabled": lan_enabled,
                "copy_after_capture": "local",
            },
        }
        save_config(config, config_path)

        image_path = screenshots / "capture.png"
        Image.new("RGB", (8, 6), "#ffffff").save(image_path)
        store = GalleryStore(config["database_path"])
        capture = store.add_capture("capture.png", image_path, 8, 6, image_path.stat().st_size)
        shared = store.set_share_enabled(capture["id"], True)

        app = create_app(config_path)
        app.config["TESTING"] = True
        app.config["BOUND_HOST"] = "0.0.0.0" if lan_enabled else "127.0.0.1"
        return temp_dir, app, config_path, shared

    def test_admin_routes_are_local_only(self):
        temp_dir, app, _config_path, _capture = self.make_app()
        self.addCleanup(temp_dir.cleanup)

        client = app.test_client()
        response = client.get("/api/captures", environ_base={"REMOTE_ADDR": "192.168.1.20"})

        self.assertEqual(response.status_code, 403)

    def test_local_file_route_serves_capture(self):
        temp_dir, app, _config_path, capture = self.make_app()
        self.addCleanup(temp_dir.cleanup)

        client = app.test_client()
        response = client.get(f"/captures/{capture['id']}/file")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/png")
        response.close()

    def test_shared_route_requires_global_lan_setting(self):
        temp_dir, app, config_path, capture = self.make_app(lan_enabled=False)
        self.addCleanup(temp_dir.cleanup)

        client = app.test_client()
        response = client.get(f"/s/{capture['share_token']}")
        self.assertEqual(response.status_code, 404)

        config = load_config(config_path)
        config["sharing"]["lan_enabled"] = True
        save_config(config, config_path)

        response = client.get(f"/s/{capture['share_token']}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/png")
        response.close()

    def test_capture_paths_must_stay_inside_screenshot_directory(self):
        temp_dir, app, config_path, _capture = self.make_app(lan_enabled=True)
        self.addCleanup(temp_dir.cleanup)
        config = load_config(config_path)

        outside_path = Path(temp_dir.name) / "outside.png"
        Image.new("RGB", (8, 6), "#ffffff").save(outside_path)
        store = GalleryStore(config["database_path"])
        outside = store.add_capture(
            "outside.png", outside_path, 8, 6, outside_path.stat().st_size
        )

        client = app.test_client()
        response = client.get(f"/captures/{outside['id']}/file")

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
