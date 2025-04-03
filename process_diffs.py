import subprocess
import re
import requests
from bs4 import BeautifulSoup
from typing import List, Optional

def get_unstaged_diff() -> str:
    """Get the diff for unstaged changes."""
    result = subprocess.run(
        ["git", "diff"],
        capture_output=True,
        text=True
    )
    return result.stdout

def extract_gallery_links(diff_content: str) -> List[str]:
    """Extract gallery links from diff content."""
    gallery_links = []

    # Look for added lines containing gallery items
    # Pattern matches lines like: +<a class="gallery-item" href="https://example.com/gallery/item">
    pattern = r'\+\s*<a\s+class="gallery-item"\s+href="([^"]+)">'

    for match in re.finditer(pattern, diff_content):
        gallery_links.append(match.group(1))

    return gallery_links

def main():
    # Get the unstaged diff
    diff_content = get_unstaged_diff()

    # Extract gallery links
    gallery_links = extract_gallery_links(diff_content)

    if gallery_links:
        print(f"Found {len(gallery_links)} new gallery items")
        # for url in gallery_links:
        #     addToFeed(url)
    else:
        print("No new gallery items found")

if __name__ == "__main__":
    main()