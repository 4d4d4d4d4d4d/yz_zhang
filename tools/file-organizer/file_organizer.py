#!/usr/bin/env python3
"""
File Organizer - A utility to organize files in directories by various criteria.

Features:
- Organize by file extension (images, documents, code, etc.)
- Organize by date (year/month)
- Organize by file size
- Dry-run mode to preview changes
- Customizable file type categories
"""

import os
import shutil
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import json


class FileOrganizer:
    """Organize files in a directory based on various criteria."""

    # Default file type categories
    FILE_CATEGORIES = {
        'Images': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp', '.ico'],
        'Documents': ['.pdf', '.doc', '.docx', '.txt', '.odt', '.rtf', '.tex', '.md'],
        'Spreadsheets': ['.xls', '.xlsx', '.csv', '.ods'],
        'Presentations': ['.ppt', '.pptx', '.odp'],
        'Videos': ['.mp4', '.avi', '.mkv', '.mov', '.flv', '.wmv', '.webm'],
        'Audio': ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a'],
        'Archives': ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz'],
        'Code': ['.py', '.js', '.java', '.cpp', '.c', '.h', '.hpp', '.cs', '.go', '.rs', '.rb'],
        'Web': ['.html', '.css', '.scss', '.sass', '.xml', '.json', '.yaml', '.yml'],
        'Executables': ['.exe', '.dll', '.so', '.dylib', '.app', '.deb', '.rpm'],
        'Fonts': ['.ttf', '.otf', '.woff', '.woff2', '.eot'],
    }

    def __init__(self, source_dir, dry_run=False, custom_categories=None):
        """
        Initialize the FileOrganizer.

        Args:
            source_dir: Directory to organize
            dry_run: If True, only show what would be done
            custom_categories: Optional dict of custom file categories
        """
        self.source_dir = Path(source_dir).resolve()
        self.dry_run = dry_run
        self.categories = custom_categories if custom_categories else self.FILE_CATEGORIES

        if not self.source_dir.exists():
            raise ValueError(f"Directory does not exist: {self.source_dir}")

        if not self.source_dir.is_dir():
            raise ValueError(f"Path is not a directory: {self.source_dir}")

    def organize_by_extension(self):
        """Organize files by their extension into categorized folders."""
        print(f"\n{'[DRY RUN] ' if self.dry_run else ''}Organizing files by extension in: {self.source_dir}\n")

        # Create extension to category mapping
        ext_to_category = {}
        for category, extensions in self.categories.items():
            for ext in extensions:
                ext_to_category[ext.lower()] = category

        files_moved = defaultdict(list)

        # Process all files in the directory (non-recursive)
        for item in self.source_dir.iterdir():
            if not item.is_file():
                continue

            ext = item.suffix.lower()
            category = ext_to_category.get(ext, 'Other')

            # Create category folder
            category_folder = self.source_dir / category

            # Move file
            target_path = category_folder / item.name

            # Handle duplicate names
            counter = 1
            while target_path.exists():
                target_path = category_folder / f"{item.stem}_{counter}{item.suffix}"
                counter += 1

            if not self.dry_run:
                category_folder.mkdir(exist_ok=True)
                shutil.move(str(item), str(target_path))

            files_moved[category].append((item.name, target_path.relative_to(self.source_dir)))

        # Print summary
        self._print_summary(files_moved)
        return files_moved

    def organize_by_date(self):
        """Organize files by their modification date (YYYY/MM folders)."""
        print(f"\n{'[DRY RUN] ' if self.dry_run else ''}Organizing files by date in: {self.source_dir}\n")

        files_moved = defaultdict(list)

        for item in self.source_dir.iterdir():
            if not item.is_file():
                continue

            # Get modification time
            mod_time = datetime.fromtimestamp(item.stat().st_mtime)
            year_month = mod_time.strftime("%Y/%B")

            # Create date folder
            date_folder = self.source_dir / year_month
            target_path = date_folder / item.name

            # Handle duplicate names
            counter = 1
            while target_path.exists():
                target_path = date_folder / f"{item.stem}_{counter}{item.suffix}"
                counter += 1

            if not self.dry_run:
                date_folder.mkdir(parents=True, exist_ok=True)
                shutil.move(str(item), str(target_path))

            files_moved[year_month].append((item.name, target_path.relative_to(self.source_dir)))

        self._print_summary(files_moved)
        return files_moved

    def organize_by_size(self):
        """Organize files by their size into Small/Medium/Large folders."""
        print(f"\n{'[DRY RUN] ' if self.dry_run else ''}Organizing files by size in: {self.source_dir}\n")

        files_moved = defaultdict(list)

        # Size thresholds (in bytes)
        SMALL_THRESHOLD = 1024 * 1024  # 1 MB
        MEDIUM_THRESHOLD = 10 * 1024 * 1024  # 10 MB

        for item in self.source_dir.iterdir():
            if not item.is_file():
                continue

            size = item.stat().st_size

            if size < SMALL_THRESHOLD:
                category = "Small (< 1MB)"
            elif size < MEDIUM_THRESHOLD:
                category = "Medium (1-10MB)"
            else:
                category = "Large (> 10MB)"

            # Create size folder
            size_folder = self.source_dir / category
            target_path = size_folder / item.name

            # Handle duplicate names
            counter = 1
            while target_path.exists():
                target_path = size_folder / f"{item.stem}_{counter}{item.suffix}"
                counter += 1

            if not self.dry_run:
                size_folder.mkdir(exist_ok=True)
                shutil.move(str(item), str(target_path))

            files_moved[category].append((item.name, target_path.relative_to(self.source_dir)))

        self._print_summary(files_moved)
        return files_moved

    def _print_summary(self, files_moved):
        """Print a summary of files moved."""
        total_files = sum(len(files) for files in files_moved.values())

        if total_files == 0:
            print("No files to organize.")
            return

        print(f"{'Would move' if self.dry_run else 'Moved'} {total_files} file(s):\n")

        for category, files in sorted(files_moved.items()):
            print(f"  {category}: {len(files)} file(s)")
            for original, target in files[:3]:  # Show first 3 files
                print(f"    - {original} → {target}")
            if len(files) > 3:
                print(f"    ... and {len(files) - 3} more")
            print()


def load_config(config_path):
    """Load custom file categories from a JSON config file."""
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: Could not load config file: {e}")
        return None


def main():
    """Main entry point for the file organizer."""
    parser = argparse.ArgumentParser(
        description="Organize files in a directory by extension, date, or size.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s /path/to/dir --by-extension
  %(prog)s /path/to/dir --by-date --dry-run
  %(prog)s /path/to/dir --by-size
  %(prog)s /path/to/dir --by-extension --config custom_categories.json
        """
    )

    parser.add_argument('directory', help='Directory to organize')

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--by-extension', action='store_true',
                      help='Organize files by extension (Images, Documents, etc.)')
    group.add_argument('--by-date', action='store_true',
                      help='Organize files by modification date (YYYY/MM)')
    group.add_argument('--by-size', action='store_true',
                      help='Organize files by size (Small/Medium/Large)')

    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be done without making changes')
    parser.add_argument('--config', help='Path to custom categories JSON file')

    args = parser.parse_args()

    # Load custom categories if provided
    custom_categories = None
    if args.config:
        custom_categories = load_config(args.config)

    try:
        organizer = FileOrganizer(args.directory, dry_run=args.dry_run,
                                 custom_categories=custom_categories)

        if args.by_extension:
            organizer.organize_by_extension()
        elif args.by_date:
            organizer.organize_by_date()
        elif args.by_size:
            organizer.organize_by_size()

        if args.dry_run:
            print("\nThis was a dry run. No files were actually moved.")
            print("Run without --dry-run to apply these changes.")

    except Exception as e:
        print(f"Error: {e}")
        return 1

    return 0


if __name__ == '__main__':
    exit(main())
