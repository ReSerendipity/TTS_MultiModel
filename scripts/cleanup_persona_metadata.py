#!/usr/bin/env python
"""上传参考音频元数据清理脚本。

清理 personas/ 目录中可能残留的临时文件、孤立元数据和不一致条目。

用法：
    python scripts/cleanup_persona_metadata.py [--dry-run]
"""

import argparse
import os
import sys


def cleanup_personas(persona_dir: str, dry_run: bool = False) -> dict:
    """清理 persona 目录中的孤立元数据。

    Args:
        persona_dir: personas 目录路径。
        dry_run: 仅报告不实际删除。

    Returns:
        清理统计字典。
    """
    stats = {
        "total_personas": 0,
        "orphan_txt": 0,
        "orphan_pt": 0,
        "empty_files": 0,
        "cleaned": 0,
    }

    if not os.path.isdir(persona_dir):
        print(f"目录不存在: {persona_dir}", file=sys.stderr)
        return stats

    for entry in os.listdir(persona_dir):
        name, ext = os.path.splitext(entry)
        full_path = os.path.join(persona_dir, entry)

        if ext == ".wav":
            stats["total_personas"] += 1
            # 检查是否有对应的 .txt
            txt_path = os.path.join(persona_dir, f"{name}.txt")

            if os.path.exists(txt_path) and os.path.getsize(txt_path) == 0:
                stats["empty_files"] += 1
                if not dry_run:
                    os.remove(txt_path)
                print(f"  清理空文件: {name}.txt")

        elif ext == ".txt":
            wav_path = os.path.join(persona_dir, f"{name}.wav")
            if not os.path.exists(wav_path):
                stats["orphan_txt"] += 1
                if not dry_run:
                    os.remove(full_path)
                print(f"  清理孤立文件: {name}.txt (无对应 .wav)")

        elif ext == ".pt":
            wav_path = os.path.join(persona_dir, f"{name}.wav")
            if not os.path.exists(wav_path):
                stats["orphan_pt"] += 1
                if not dry_run:
                    os.remove(full_path)
                print(f"  清理孤立文件: {name}.pt (无对应 .wav)")

    stats["cleaned"] = stats["orphan_txt"] + stats["orphan_pt"] + stats["empty_files"]
    return stats


def main():
    parser = argparse.ArgumentParser(description="Persona 元数据清理")
    parser.add_argument("--dry-run", action="store_true", help="仅报告不实际删除")
    args = parser.parse_args()

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    persona_dir = os.path.join(project_root, "personas")

    print(f"Persona 目录: {persona_dir}")
    print(f"模式: {'dry-run（仅报告）' if args.dry_run else '实际清理'}")
    print()

    stats = cleanup_personas(persona_dir, dry_run=args.dry_run)

    print()
    print(f"总 persona 数: {stats['total_personas']}")
    print(f"孤立 .txt 文件: {stats['orphan_txt']}")
    print(f"孤立 .pt 文件: {stats['orphan_pt']}")
    print(f"空文件: {stats['empty_files']}")
    print(f"总清理数: {stats['cleaned']}")


if __name__ == "__main__":
    main()
