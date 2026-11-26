"""Read-only readiness checks for public GitHub repositories."""

import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

MAX_FILES = 20
MAX_FILE_SIZE = 120_000
MAX_DIRS = 6
SOURCE = re.compile(r"\.(?:js|jsx|ts|tsx|py|go|rs|java|kt|rb|php|sh|yml|yaml|json|toml|ini|cfg|conf|properties|md|txt|bat|cmd|ps1|vbs)$", re.I)
SKIP = re.compile(r"(?:^|/)(?:node_modules|vendor|dist|build|\.git|\.next|coverage)/|(?:^|/)(?:package-lock\.json|yarn\.lock|pnpm-lock\.yaml|Cargo\.lock|poetry\.lock)$", re.I)
MANIFEST = re.compile(r"(?:^|/)(?:package\.json|requirements(?:-[^/]*)?\.txt|pyproject\.toml|Pipfile|go\.mod|Cargo\.toml|pom\.xml|build\.gradle(?:\.kts)?|Gemfile|composer\.json)$", re.I)
WINDOWS = re.compile(r"\.(?:bat|cmd|ps1|vbs)$", re.I)
START = re.compile(r"(?:^|/)(?:start|run|serve|dev|main|app|server)(?:\.[^/]+)?$", re.I)
HARD_PATH = re.compile(r"\b[A-Za-z]:\\(?:Users|Program Files|Projects|Work|Dev)\\[^\s\"'`]+|/(?:Users|home)/[^\s\"'`/]+(?:/[^\s\"'`]+)?")
SECRET_RULES = [
    ("OpenAI 风格密钥", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
    ("AWS Access Key ID", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("Bearer 令牌", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{24,}\b", re.I)),
    ("私钥", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("GitHub 令牌", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b")),
]
POINTS = {"critical": 25, "high": 18, "medium": 8, "low": 4}


class ScanError(Exception):
    pass


def parse_github_url(value):
    if not isinstance(value, str):
        raise ScanError("请输入 GitHub 仓库链接。")
    parsed = urlparse(value.strip())
    if parsed.scheme != "https" or parsed.hostname not in ("github.com", "www.github.com") or parsed.username or parsed.password or parsed.port or parsed.query or parsed.fragment:
        raise ScanError("目前只支持 github.com 的 HTTPS 公开仓库链接。")
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) != 2 or not all(re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in parts):
        raise ScanError("链接格式应为 https://github.com/用户名/仓库名。")
    owner, repo = parts
    repo = re.sub(r"\.git$", "", repo, flags=re.I)
    if not repo:
        raise ScanError("仓库名不能为空。")
    return {"owner": owner, "repo": repo, "url": f"https://github.com/{owner}/{repo}"}


class EmbeddedDataParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_data = False
        self.data = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        self.in_data = tag == "script" and attributes.get("data-target") == "react-app.embeddedData"

    def handle_data(self, data):
        if self.in_data:
            self.data = json.loads(data)

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_data = False


def github_page(url):
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(request, timeout=12) as response:
            parser = EmbeddedDataParser()
            parser.feed(response.read().decode("utf-8"))
            if parser.data is None:
                raise ScanError("无法读取 GitHub 仓库页面。")
            return parser.data["payload"]
    except HTTPError as error:
        if error.code == 404:
            raise ScanError("仓库不存在或不是公开仓库。") from error
        if error.code in (403, 429):
            raise ScanError("GitHub 页面暂时限制访问，请稍后重试。") from error
        raise ScanError(f"GitHub 请求失败（HTTP {error.code}）。") from error
    except URLError as error:
        raise ScanError("无法连接 GitHub，请检查网络后重试。") from error


def github_file(repo, branch, path):
    url = f"https://raw.githubusercontent.com/{repo['owner']}/{repo['repo']}/{quote(branch, safe='')}/{quote(path, safe='/')}"
    request = Request(url, headers={"User-Agent": "repo-readiness/1.0"})
    with urlopen(request, timeout=12) as response:
        content = response.read(MAX_FILE_SIZE + 1)
    return content.decode("utf-8", errors="replace") if len(content) <= MAX_FILE_SIZE else None


def directory_items(repo, branch, directory):
    url = f"{repo['url']}/tree/{quote(branch, safe='')}/{quote(directory['path'], safe='/')}"
    return github_page(url)["codeViewTreeRoute"]["tree"]["items"]


def make_finding(identifier, severity, title, detail, paths=()):
    return {"id": identifier, "severity": severity, "title": title, "detail": detail, "paths": list(dict.fromkeys(paths))[:8]}


def priority(path):
    name = path.rsplit("/", 1)[-1]
    if re.fullmatch(r"readme(?:\.[^/]+)?", name, re.I):
        return 0
    if MANIFEST.search(path):
        return 1
    if re.fullmatch(r"\.env(?:\.[^/]+)?", name, re.I):
        return 2
    if WINDOWS.search(path) or START.search(path):
        return 3
    if re.search(r"(?:^|/)(?:config|settings|application)(?:\.[^/]+)?$", path, re.I):
        return 4
    return 5


def evaluate_tree(entries, contents, *, tree_truncated=False, skipped_large_files=0, unreadable_files=0):
    files = [entry for entry in entries if entry.get("type") == "blob"]
    paths = [entry["path"] for entry in files]
    root_readme = next((path for path in paths if re.fullmatch(r"readme(?:\.[^/]+)?", path, re.I)), None)
    readme = contents.get(root_readme) if root_readme else None
    manifests = [path for path in paths if MANIFEST.search(path)]
    windows_scripts = [path for path in paths if WINDOWS.search(path)]
    start_files = [path for path in paths if START.search(path) and not WINDOWS.search(path)]
    package_files = [path for path in paths if re.search(r"(?:^|/)package\.json$", path, re.I)]
    findings = []
    if not root_readme:
        findings.append(make_finding("readme-missing", "high", "缺少根目录 README", "需要提供项目用途、安装和启动说明。"))
    elif readme is None:
        findings.append(make_finding("readme-unread", "medium", "README 未能读取", "已发现 README，但本次扫描未取得内容。", [root_readme]))
    else:
        if len(readme.strip()) < 120:
            findings.append(make_finding("readme-short", "medium", "README 内容较少", "建议补充用途、环境要求、安装及启动步骤。", [root_readme]))
        if not re.search(r"安装|依赖|install|setup|requirements", readme, re.I):
            findings.append(make_finding("install-doc-missing", "low", "缺少安装说明", "README 中未识别到安装或依赖说明。", [root_readme]))
        if not re.search(r"启动|运行|使用|quick.?start|getting started|usage|run|start", readme, re.I):
            findings.append(make_finding("run-doc-missing", "medium", "缺少运行说明", "README 中未识别到启动或使用步骤。", [root_readme]))
    if not manifests:
        findings.append(make_finding("manifest-missing", "high", "未找到常见依赖清单", "未发现 package.json、requirements.txt、pyproject.toml 等常见清单。"))
    package_scripts = []
    for path in package_files:
        if path not in contents:
            continue
        try:
            scripts = json.loads(contents[path]).get("scripts", {})
            if isinstance(scripts, dict):
                package_scripts += [f"{path}: {name}" for name, command in scripts.items() if name in ("start", "dev", "serve", "build", "test") and isinstance(command, str)]
        except (ValueError, AttributeError, TypeError):
            findings.append(make_finding("package-invalid", "medium", "package.json 格式错误", "无法解析项目脚本与依赖。", [path]))
    has_start_script = any(item.rsplit(": ", 1)[-1] in ("start", "dev", "serve") for item in package_scripts)
    readme_has_run = bool(readme and re.search(r"npm|pnpm|yarn|pip|python|uv|go run|cargo run|docker compose|\./(?:start|run)|启动|运行", readme, re.I))
    if not start_files and not has_start_script and not readme_has_run:
        findings.append(make_finding("startup-missing", "medium", "启动入口不明确", "未识别到常见启动文件、package.json 启动脚本或 README 运行命令。"))
    if windows_scripts:
        findings.append(make_finding("windows-scripts", "medium", "包含 Windows 专用脚本", "在 Linux/macOS 部署前需要确认替代启动方式。", windows_scripts))
        if not start_files and not has_start_script:
            findings.append(make_finding("windows-only", "medium", "可能依赖 Windows 启动", "未识别到跨平台启动脚本。", windows_scripts))
    env_files = [path for path in paths if re.search(r"(?:^|/)\.env(?:\.[^/]+)?$", path, re.I) and not re.search(r"\.env\.(?:example|sample|template)$", path, re.I)]
    if env_files:
        findings.append(make_finding("env-committed", "critical", "仓库包含环境变量文件", "请检查是否包含真实凭据；不要将实际密钥提交到仓库。", env_files))
    secret_paths = {}
    hard_paths = set()
    for path, content in contents.items():
        for name, pattern in SECRET_RULES:
            if pattern.search(content):
                secret_paths.setdefault(name, []).append(path)
        if HARD_PATH.search(content):
            hard_paths.add(path)
    for name, found in secret_paths.items():
        findings.append(make_finding(f"secret-{name}", "critical", f"疑似{name}泄露", "检测到符合密钥特征的内容；可能误报，请人工核查并轮换真实凭据。结果不会展示密钥原文。", found))
    if hard_paths:
        findings.append(make_finding("hard-path", "medium", "发现疑似硬编码绝对路径", "请改用相对路径或环境变量，并核查是否包含本机目录。", sorted(hard_paths)))
    score = max(0, 100 - sum(POINTS[item["severity"]] for item in findings))
    readiness = "较好" if score >= 85 else "需完善" if score >= 60 else "暂不建议接入"
    categories = [
        {"key": "documentation", "label": "文档与依赖", "status": "attention" if not root_readme or not manifests else "checked", "items": ([root_readme] if root_readme else ["未找到 README"]) + manifests[:5]},
        {"key": "startup", "label": "启动方式", "status": "attention" if any(item["id"] in ("startup-missing", "windows-only") for item in findings) else "checked", "items": start_files[:5] + package_scripts[:5]},
        {"key": "platform", "label": "平台兼容", "status": "attention" if windows_scripts else "checked", "items": windows_scripts[:5]},
        {"key": "paths", "label": "硬编码路径", "status": "attention" if hard_paths else "checked", "items": sorted(hard_paths)[:5]},
        {"key": "secrets", "label": "敏感信息", "status": "attention" if env_files or secret_paths else "checked", "items": (env_files + [path for found in secret_paths.values() for path in found])[:5]},
    ]
    eligible_count = sum(1 for entry in files if SOURCE.search(entry["path"]) and not SKIP.search(entry["path"]) and entry.get("size", 0) <= MAX_FILE_SIZE)
    return {"score": score, "readiness": readiness, "findings": sorted(findings, key=lambda item: -POINTS[item["severity"]]), "categories": categories,
            "coverage": {"totalFiles": len(files), "scannedFiles": len(contents), "eligibleFiles": eligible_count, "treeTruncated": tree_truncated, "skippedLargeFiles": skipped_large_files, "unreadableFiles": unreadable_files, "limited": tree_truncated or len(contents) < eligible_count},
            "advice": "优先人工核查疑似凭据并轮换真实密钥，再完善启动与文档。" if any(item["severity"] == "critical" for item in findings) else "先处理高优先级风险，补齐可复现的安装和启动步骤，再重新扫描。" if score < 85 else "基础接入条件较好；仍建议在目标环境实际安装、启动并运行测试。"}


def analyze_repository(value):
    repo = parse_github_url(value)
    page = github_page(repo["url"])
    route = page["codeViewRepoRoute"]
    branch = route["refInfo"]["name"]
    if not branch:
        raise ScanError("空仓库没有可扫描的默认分支。")
    commit = route["refInfo"].get("currentOid")
    if not commit:
        raise ScanError("无法确认默认分支的 commit，请稍后重试。")
    entries = []
    pending = [item for item in route["tree"]["items"] if item["contentType"] == "directory"]
    entries.extend({"path": item["path"], "type": "blob", "size": 0} for item in route["tree"]["items"] if item["contentType"] == "file")
    visited = 0
    unreadable_dirs = 0
    with ThreadPoolExecutor(max_workers=5) as pool:
        while pending and visited < MAX_DIRS:
            batch = pending[:min(5, MAX_DIRS - visited)]
            del pending[:len(batch)]
            visited += len(batch)
            results = list(pool.map(lambda item: read_directory(repo, commit, item), batch))
            for items in results:
                if items is None:
                    unreadable_dirs += 1
                    continue
                entries.extend({"path": item["path"], "type": "blob", "size": 0} for item in items if item["contentType"] == "file")
                pending.extend(item for item in items if item["contentType"] == "directory" and not SKIP.search(item["path"] + "/"))
    source_files = [entry for entry in entries if entry.get("type") == "blob" and SOURCE.search(entry["path"]) and not SKIP.search(entry["path"])]
    selected = sorted(source_files, key=lambda entry: (priority(entry["path"]), len(entry["path"]), entry["path"]))[:MAX_FILES]
    contents = {}
    unreadable = 0
    large = 0
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(lambda entry: read_file(repo, commit, entry), selected))
    for entry, result in zip(selected, results):
        kind, content = result
        if kind == "ok":
            contents[entry["path"]] = content
        elif kind == "large":
            large += 1
        else:
            unreadable += 1
    return {"repository": {**repo, "description": page.get("sidebarAbout", {}).get("description") or "", "defaultBranch": branch, "commit": commit},
            **evaluate_tree(entries, contents, tree_truncated=bool(pending or unreadable_dirs), skipped_large_files=large, unreadable_files=unreadable),
            "scannedAt": datetime.now(timezone.utc).isoformat()}


def read_directory(repo, branch, directory):
    try:
        return directory_items(repo, branch, directory)
    except (ScanError, KeyError, ValueError):
        return None


def read_file(repo, branch, entry):
    try:
        content = github_file(repo, branch, entry["path"])
        return ("ok", content) if content is not None else ("large", None)
    except (HTTPError, URLError, ValueError):
        return ("unreadable", None)
