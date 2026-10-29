import unittest

from CameraView.config import SceneConfig


class SceneConfigTests(unittest.TestCase):
    def test_alias_lookup(self):
        config = SceneConfig({
            "layout": {"matrix": ["1"], "aliases": {"front": "1"}},
            "cameras": {"front": {"direction": [0, 0, 1]}},
        })
        self.assertEqual(config.for_pad("cameras", "1")["direction"], [0, 0, 1])

    def test_requires_layout(self):
        with self.assertRaisesRegex(ValueError, "layout.matrix"):
            SceneConfig({})


if __name__ == "__main__":
    unittest.main()
