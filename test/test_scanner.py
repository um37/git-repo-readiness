import unittest

from scanner import ScanError, evaluate_tree, parse_github_url


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


if __name__ == "__main__":
    unittest.main()
