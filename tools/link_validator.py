#!/usr/bin/env python3
"""Comprehensive link validator for repository documentation."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import NamedTuple
from urllib.parse import urlparse

class LinkIssue(NamedTuple):
    file: str
    line_num: int | None
    link: str
    issue_type: str  # 'broken_relative', 'malformed_anchor', 'invalid_asset', etc.
    details: str

def find_documentation_files() -> list[Path]:
    """Find all markdown files in repository."""
    root = Path(__file__).parent.parent
    files = []
    
    # Define exclusion patterns
    exclude_dirs = {'.venv', 'node_modules', '__pycache__', '.git', '.egg-info', 'dist', 'build'}
    
    def should_exclude(path: Path) -> bool:
        """Check if path should be excluded."""
        for part in path.parts:
            if part in exclude_dirs or part.endswith('.egg-info'):
                return True
        return False
    
    # Root markdown files
    for f in root.glob("*.md"):
        if not should_exclude(f):
            files.append(f)
    
    # Documentation directory
    for f in root.glob("docs/**/*.md"):
        if not should_exclude(f):
            files.append(f)
    
    # Scripts and other directories
    for f in root.glob("scripts/**/*.md"):
        if not should_exclude(f):
            files.append(f)
    
    # READMEs
    for f in root.glob("**/README.md"):
        if not should_exclude(f) and f not in files:
            files.append(f)
    
    return sorted(files)

def extract_links_from_markdown(content: str, file_path: Path) -> list[tuple[int, str, str]]:
    """Extract all links from markdown content.
    
    Returns: list of (line_num, link_type, link_target) tuples.
    """
    links = []
    root = Path(__file__).parent.parent
    
    for line_num, line in enumerate(content.split('\n'), 1):
        # Markdown links [text](url)
        for match in re.finditer(r'\[([^\]]*)\]\(([^)]+)\)', line):
            link = match.group(2)
            links.append((line_num, 'markdown', link))
        
        # Image references ![alt](url)
        for match in re.finditer(r'!\[([^\]]*)\]\(([^)]+)\)', line):
            link = match.group(2)
            links.append((line_num, 'image', link))
        
        # HTML image tags
        for match in re.finditer(r'<img[^>]+src=(["\'])([^"\']+)\1', line):
            link = match.group(2)
            links.append((line_num, 'html_img', link))
        
        # HTML links
        for match in re.finditer(r'<a[^>]+href=(["\'])([^"\']+)\1', line):
            link = match.group(2)
            links.append((line_num, 'html_link', link))
    
    return links

def is_external_link(link: str) -> bool:
    """Check if link is external (http, https, etc.)."""
    return link.startswith(('http://', 'https://', 'ftp://', 'mailto:'))

def validate_relative_link(link: str, source_file: Path, root: Path) -> LinkIssue | None:
    """Validate relative link exists and is accessible."""
    
    # Handle anchor-only links
    if link.startswith('#'):
        return None  # Skip anchor-only validation for now
    
    # Split link and anchor
    if '#' in link:
        path_part, anchor = link.split('#', 1)
    else:
        path_part = link
        anchor = None
    
    # Resolve relative path
    if path_part:
        # Link is relative to source file directory
        resolved = (source_file.parent / path_part).resolve()
        
        # Check if file exists
        if not resolved.exists():
            return LinkIssue(
                file=str(source_file.relative_to(root)),
                line_num=None,
                link=link,
                issue_type='broken_relative_path',
                details=f"File does not exist: {path_part} (resolved to {resolved})"
            )
        
        # Check if it's a directory (shouldn't end with path-like pattern)
        if resolved.is_dir() and not path_part.endswith('/'):
            pass  # Allow directory references
    
    return None

def check_asset_exists(asset_path: str, source_file: Path, root: Path) -> LinkIssue | None:
    """Check if referenced asset (image, SVG, etc.) exists."""
    
    if not asset_path or asset_path.startswith(('http://', 'https://', 'data:')):
        return None  # Skip external and data URLs
    
    # Remove query params and anchors
    base_path = asset_path.split('?')[0].split('#')[0]
    
    resolved = (source_file.parent / base_path).resolve()
    
    if not resolved.exists():
        return LinkIssue(
            file=str(source_file.relative_to(root)),
            line_num=None,
            link=asset_path,
            issue_type='missing_asset',
            details=f"Asset not found: {base_path} (resolved to {resolved})"
        )
    
    return None

def validate_file_links(file_path: Path, root: Path) -> list[LinkIssue]:
    """Validate all links in a single file."""
    issues = []
    
    try:
        content = file_path.read_text(encoding='utf-8')
    except Exception as e:
        return [LinkIssue(
            file=str(file_path.relative_to(root)),
            line_num=None,
            link='',
            issue_type='read_error',
            details=str(e)
        )]
    
    links = extract_links_from_markdown(content, file_path)
    
    for line_num, link_type, link in links:
        # Skip external links for now
        if is_external_link(link):
            # Could validate external links with HTTP requests, but skipping for speed
            continue
        
        # Skip fragment-only links
        if link.startswith('#'):
            continue
        
        # Validate relative links
        if link_type in ('image', 'html_img'):
            issue = check_asset_exists(link, file_path, root)
            if issue:
                issues.append(LinkIssue(
                    file=issue.file,
                    line_num=line_num,
                    link=issue.link,
                    issue_type=issue.issue_type,
                    details=issue.details
                ))
        elif link_type in ('markdown', 'html_link'):
            issue = validate_relative_link(link, file_path, root)
            if issue:
                issues.append(LinkIssue(
                    file=issue.file,
                    line_num=line_num,
                    link=issue.link,
                    issue_type=issue.issue_type,
                    details=issue.details
                ))
    
    return issues

def main() -> None:
    """Run comprehensive link validation."""
    root = Path(__file__).parent.parent
    all_files = find_documentation_files()
    
    # Further filter to only include files under our repo root and not in .venv/node_modules
    files = []
    for f in all_files:
        try:
            # Check if file is under root
            f.relative_to(root)
            # Skip if any parent dir is a venv or excluded
            if '.venv' not in str(f) and 'node_modules' not in str(f) and '.egg-info' not in str(f):
                files.append(f)
        except ValueError:
            pass  # File is outside root
    
    all_issues = []
    files_checked = 0
    links_checked = 0
    assets_checked = 0
    
    print(f"Scanning {len(files)} documentation files...\n")
    
    for file_path in files:
        issues = validate_file_links(file_path, root)
        all_issues.extend(issues)
        files_checked += 1
        
        if file_path.suffix in ('.md',):
            try:
                content = file_path.read_text(encoding='utf-8')
                links = extract_links_from_markdown(content, file_path)
                links_checked += len([l for l in links if not is_external_link(l[2])])
                assets_checked += len([l for l in links if l[1] in ('image', 'html_img')])
            except:
                pass
    
    print(f"\n=== Link Validation Report ===")
    print(f"Files scanned: {files_checked}")
    print(f"Documentation files checked: {len(files)}")
    print(f"Relative links checked: {links_checked}")
    print(f"Asset references checked: {assets_checked}")
    
    # Categorize issues
    issues_by_type = {}
    for issue in all_issues:
        issues_by_type.setdefault(issue.issue_type, []).append(issue)
    
    if all_issues:
        print(f"\n=== Issues Found: {len(all_issues)} ===\n")
        for issue_type, issues in sorted(issues_by_type.items()):
            print(f"{issue_type.upper()} ({len(issues)} issues):")
            for issue in sorted(set(issues), key=lambda x: (x.file, x.link))[:10]:  # Show up to 10
                print(f"  {issue.file}: {issue.link}")
                print(f"    {issue.details}")
            if len(issues) > 10:
                print(f"  ... and {len(issues) - 10} more")
            print()
        print(f"RESULT: FAILED - {len(all_issues)} issues found")
        return 1
    else:
        print(f"\nRESULT: PASSED - No link validation issues found")
        return 0

if __name__ == '__main__':
    exit(main())
