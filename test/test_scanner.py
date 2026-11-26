import unittest
from unittest.mock import patch

from scanner import EmbeddedDataParser, ScanError, analyze_repository, evaluate_tree, parse_github_url


def entry(path):
    return {"path": path, "type": "blob", "size": 100}


class ScannerTests(unittest.TestCase):
    def test_url_requires_public_github_shape(self):
        self.assertEqual(parse_github_url("https://github.com/example/project.git")["repo"], "project")
        for value in ("http://github.com/a/b", "https://evil.example/a/b", "https://github.com/a/b/tree/main", "https://github.com/a/b?x=1"):
            with self.subTest(value=value), self.assertRaises(ScanError):
                parse_github_url(value)

    def test_missing_basics_and_windows_script(self):
        report = evaluate_tree([entry("run.bat")], {"run.bat": "echo hi"})
        ids = {item["id"] for item in report["findings"]}
        self.assertTrue({"readme-missing", "manifest-missing", "windows-scripts", "windows-only"}.issubset(ids))
        self.assertLess(report["score"], 60)

    def test_redacts_secret_and_detects_path(self):
        secret = "sk-" + "a" * 32
        report = evaluate_tree([entry("README.md"), entry("package.json"), entry("app.py")], {
            "README.md": "安装依赖，然后运行项目。" * 10,
            "package.json": '{"scripts":{"start":"node app.js"}}',
            "app.py": f'token = "{secret}"\npath = "C:\\Users\\alice\\project"',
        })
        ids = {item["id"] for item in report["findings"]}
        self.assertIn("secret-OpenAI 风格密钥", ids)
        self.assertIn("hard-path", ids)
        self.assertNotIn(secret, str(report))

    def test_coverage_warns_when_scan_is_partial(self):
        report = evaluate_tree([entry("README.md"), entry("app.py")], {"README.md": "安装运行" * 30})
        self.assertTrue(report["coverage"]["limited"])
        self.assertEqual(report["coverage"]["scannedFiles"], 1)

    def test_public_page_scan_without_rest_api(self):
        parser = EmbeddedDataParser()
        parser.feed('<script type="application/json" data-target="react-app.embeddedData">{"payload":{"ok":true}}</script>')
        self.assertTrue(parser.data["payload"]["ok"])
        root = {"codeViewRepoRoute": {"refInfo": {"name": "main"}, "tree": {"items": [
            {"path": "README.md", "contentType": "file"},
            {"path": "package.json", "contentType": "file"},
        ]}}, "sidebarAbout": {"description": "demo"}}
        files = {"README.md": "安装依赖，然后运行项目。" * 10, "package.json": '{"scripts":{"start":"node app.js"}}'}
        with patch("scanner.github_page", return_value=root), patch("scanner.github_file", side_effect=lambda repo, branch, path: files[path]):
            report = analyze_repository("https://github.com/example/demo")
        self.assertEqual(report["score"], 100)
        self.assertEqual(report["coverage"]["scannedFiles"], 2)
        self.assertFalse(report["coverage"]["limited"])


if __name__ == "__main__":
    unittest.main()
