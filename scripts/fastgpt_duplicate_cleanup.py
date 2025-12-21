import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import List, Tuple

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.config import settings
from app.utils.fastgpt_cleaner import FastGPTCleaner


def list_available_apps() -> List[Tuple[str, str]]:
    """列出配置中支持FastGPT的应用"""
    apps = []
    for app in settings.FEISHU_APPS:
        has_fastgpt = bool(getattr(app, "fastgpt_url", None) and getattr(app, "fastgpt_key", None))
        if has_fastgpt:
            apps.append((app.app_id, getattr(app, "app_name", "未命名应用")))
    return apps


async def run_cleanup(app_id: str, dry_run: bool) -> dict:
    """执行清理任务"""
    cleaner = FastGPTCleaner(app_id=app_id, dry_run=dry_run)
    try:
        return await cleaner.clean_duplicate_collections()
    finally:
        await cleaner.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="扫描FastGPT/Aichat目录并删除同名重复文件，只保留最新版本"
    )
    parser.add_argument(
        "--app-id",
        help="需要清理的飞书应用ID（必填）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="预览模式，只记录拟删除的文件，不执行删除",
    )
    parser.add_argument(
        "--list-apps",
        action="store_true",
        help="列出当前配置中可执行清理的应用并退出",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    available_apps = list_available_apps()

    if args.list_apps:
        if not available_apps:
            print("未找到配置了FastGPT的应用。请先在config中补全fastgpt_url/fastgpt_key。")
            return
        print("可用的FastGPT应用：")
        for app_id, app_name in available_apps:
            print(f"- {app_id}\t{app_name}")
        return

    if not args.app_id:
        print("请通过 --app-id 指定需要清理的应用。可先使用 --list-apps 查看可用列表。")
        return

    if args.app_id not in [app_id for app_id, _ in available_apps]:
        print(f"app_id={args.app_id} 未配置FastGPT访问参数，无法执行清理。")
        return

    result = asyncio.run(run_cleanup(args.app_id, args.dry_run))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

