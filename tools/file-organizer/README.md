# File Organizer

A simple yet powerful Python utility to organize files in directories by various criteria.

## Features

- **Organize by Extension**: Automatically categorizes files into folders like Images, Documents, Code, etc.
- **Organize by Date**: Groups files by modification date (YYYY/Month folders)
- **Organize by Size**: Sorts files into Small/Medium/Large categories
- **Dry-run Mode**: Preview changes before applying them
- **Custom Categories**: Define your own file type categories via JSON config
- **Duplicate Handling**: Automatically handles files with duplicate names

## Installation

No external dependencies required! Just Python 3.6+

```bash
# Clone the repository
git clone <repository-url>
cd yz_zhang

# Make the script executable (optional)
chmod +x file_organizer.py
```

## Usage

### Basic Usage

```bash
# Organize by file extension
python file_organizer.py /path/to/directory --by-extension

# Organize by modification date
python file_organizer.py /path/to/directory --by-date

# Organize by file size
python file_organizer.py /path/to/directory --by-size
```

### Dry Run (Preview Mode)

Always recommended to run with `--dry-run` first to see what will happen:

```bash
python file_organizer.py /path/to/directory --by-extension --dry-run
```

### Custom Categories

Create a custom configuration file to define your own file categories:

```bash
python file_organizer.py /path/to/directory --by-extension --config my_categories.json
```

See `example_config.json` for the configuration format.

## Examples

### Example 1: Organize Downloads Folder

```bash
python file_organizer.py ~/Downloads --by-extension --dry-run
```

This will show you how your files would be organized into categories like:
- Images/ (jpg, png, gif, etc.)
- Documents/ (pdf, docx, txt, etc.)
- Videos/ (mp4, avi, mkv, etc.)
- And more...

### Example 2: Organize Photos by Date

```bash
python file_organizer.py ~/Pictures --by-date
```

This will organize your photos into folders like:
- 2025/January/
- 2025/February/
- 2024/December/

### Example 3: Clean Up Large Files

```bash
python file_organizer.py /path/to/folder --by-size
```

This will separate files into:
- Small (< 1MB)/
- Medium (1-10MB)/
- Large (> 10MB)/

## Default File Categories

The organizer recognizes these file types by default:

- **Images**: jpg, jpeg, png, gif, bmp, svg, webp, ico
- **Documents**: pdf, doc, docx, txt, odt, rtf, tex, md
- **Spreadsheets**: xls, xlsx, csv, ods
- **Presentations**: ppt, pptx, odp
- **Videos**: mp4, avi, mkv, mov, flv, wmv, webm
- **Audio**: mp3, wav, flac, aac, ogg, wma, m4a
- **Archives**: zip, rar, 7z, tar, gz, bz2, xz
- **Code**: py, js, java, cpp, c, h, hpp, cs, go, rs, rb
- **Web**: html, css, scss, sass, xml, json, yaml, yml
- **Executables**: exe, dll, so, dylib, app, deb, rpm
- **Fonts**: ttf, otf, woff, woff2, eot

Files that don't match any category go into an "Other" folder.

## Custom Configuration

Create a JSON file with your custom categories:

```json
{
  "MyImages": [".jpg", ".png", ".heic"],
  "MyDocuments": [".pdf", ".docx"],
  "ProjectFiles": [".psd", ".ai", ".sketch"]
}
```

Then use it with:

```bash
python file_organizer.py /path/to/dir --by-extension --config custom.json
```

## Safety Features

- **Dry-run mode**: Test before making changes
- **Duplicate handling**: Automatically renames files if duplicates exist
- **Non-recursive**: Only processes files in the specified directory (not subdirectories)
- **Validation**: Checks that the directory exists before proceeding

## Use Cases

- Clean up messy Downloads folders
- Organize photo libraries by date
- Sort project files by type
- Identify large files taking up space
- Prepare files for backup or archival
- Maintain organized work directories

## Requirements

- Python 3.6 or higher
- No external dependencies (uses only standard library)

## License

MIT License - Feel free to use and modify as needed.

## Contributing

Suggestions and improvements are welcome! Feel free to:
- Report bugs
- Suggest new features
- Submit pull requests

## Future Enhancements

Potential features for future versions:
- Recursive organization (organize subdirectories)
- Undo functionality
- Pattern-based filtering (ignore certain files)
- Move vs Copy mode
- Integration with cloud storage
- GUI interface
