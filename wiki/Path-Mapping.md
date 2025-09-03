# Path Mapping Configuration

## Overview

Path mapping is a feature that allows you to configure how local file paths are mapped to paths in the GitLab repository. This is useful when you have different folder structures locally versus in the repository.

## How Path Mapping Works

When PatchWatch processes a file, it analyzes the file path and applies mappings to determine where the file should be placed in the GitLab repository:

1. File path is analyzed to extract the source path
2. Source path is matched against configured mappings
3. Matching mapping is applied to generate the target path
4. File is synchronized to `data/{target_path}/{filename}` in GitLab

## Configuration Methods

### 1. Web Interface (Recommended)

The easiest way to configure path mappings is through the web interface:

1. Open the PatchWatch web interface
2. Click on the "🗂️ Path Mapping Configuration" section
3. Add, modify, or remove path mappings as needed
4. Click "💾 Save Path Mappings"

### 2. Configuration File

You can also configure path mappings directly in the `working_config.json` file:

```json
{
  "path_mappings": [
    ["local_path", "git_path"],
    ["htdocs", "data/htdocs"],
    ["script", "data/script"]
  ]
}
```

## Path Mapping Format

Each path mapping is a pair of strings:
- **Source Path**: The path relative to the `to/` folder in your date structure
- **Target Path**: The path relative to the repository root (usually under `data/`)

### Examples

| Source Path | Target Path | Description |
|-------------|-------------|-------------|
| `htdocs` | `data/htdocs` | Maps local htdocs folder to data/htdocs in Git |
| `script` | `data/script` | Maps local script folder to data/script in Git |
| `home/storage/local` | `data/home/storage/local` | Maps full path to data/home/storage/local in Git |
| `custom/module` | `data/custom/module` | Custom module mapping |

## Default Mappings

If no path mappings are configured, the following default mappings are used:

```json
[
  ["usr/local/httpd/htdocs", "htdocs"],
  ["usr/local/asterisk/etc/asterisk/script", "script"],
  ["home/storage/local", "home/storage/local"],
  ["htdocs", "htdocs"],
  ["script", "script"]
]
```

## Priority Rules

Path mappings are applied in order, with longer paths taking precedence over shorter ones. This ensures that more specific mappings are applied before general ones.

For example:
1. `usr/local/httpd/htdocs` (more specific) is checked before `htdocs` (more general)
2. If a file path starts with `usr/local/httpd/htdocs`, the first mapping is used
3. If a file path starts with `htdocs` but not the longer path, the second mapping is used

## Best Practices

1. **Use descriptive paths**: Make your path mappings clear and descriptive
2. **Order matters**: Place more specific mappings before general ones
3. **Test your mappings**: Use the web interface to test and verify your mappings
4. **Backup configuration**: Always backup your configuration before making changes
5. **Document custom mappings**: Keep documentation of any custom mappings you create

## Troubleshooting

### Common Issues

1. **Files not syncing**: Check that your path mappings cover the file paths you're using
2. **Incorrect target paths**: Verify that your source and target paths are correctly specified
3. **Mapping conflicts**: Ensure longer paths are listed before shorter ones

### Debugging Tips

1. Check the logs for path analysis information
2. Use the web interface to view current mappings
3. Test with a small set of files before applying to large directories