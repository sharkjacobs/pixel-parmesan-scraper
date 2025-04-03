import xml.etree.ElementTree as ET
import os.path
import subprocess
import re
import requests
from bs4 import BeautifulSoup
from typing import List, Optional, Tuple, Set


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


def fetch_html_content(url: str) -> Optional[str]:
    """Fetch HTML content from a URL."""
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an error for bad responses
        return response.text
    except requests.RequestException as e:
        print(f"Error fetching {url}: {e}")
        return None


def load_or_create_feed(feed_path: str) -> Tuple[ET.Element, ET.Element, Set[str], Optional[ET.ElementTree]]:
    """
    Load an existing RSS feed or create a new one if it doesn't exist.

    Returns:
        Tuple containing:
        - root element
        - channel element
        - set of existing GUIDs
        - ElementTree object or None for new feeds
    """
    existing_guids = set()

    if os.path.exists(feed_path):
        try:
            tree = ET.parse(feed_path)
            root = tree.getroot()
            channel = root.find('channel')

            # Extract all existing GUIDs to check for duplicates
            for item in channel.findall('item'):
                guid_elem = item.find('guid')
                if guid_elem is not None and guid_elem.text:
                    existing_guids.add(guid_elem.text)

            return root, channel, existing_guids, tree
        except Exception as e:
            print(f"Error parsing existing RSS feed: {e}")
            # Fall through to create a new feed

    # Create new RSS feed
    root = ET.Element('rss', version='2.0')
    channel = ET.SubElement(root, 'channel')

    # Add feed metadata
    title = ET.SubElement(channel, 'title')
    title.text = 'Pixel Parmesan'

    link = ET.SubElement(channel, 'link')
    link.text = 'https://pixelparmesan.com'

    description = ET.SubElement(channel, 'description')
    description.text = 'scraped RSS feed from pixelparmesan.com'

    return root, channel, existing_guids, None


def create_feed_item(gallery_item, source_url: str) -> Tuple[Optional[ET.Element], Optional[str]]:
    """
    Create an RSS feed item from a gallery item.

    Args:
        gallery_item: BeautifulSoup element containing the gallery item
        source_url: The URL where the item was found

    Returns:
        Tuple containing:
        - new RSS item element or None if invalid
        - GUID string or None if invalid
    """
    # Extract title - required element
    title_elem = gallery_item.select_one('.gallery_item-title')
    if not title_elem:
        return None, None  # Skip if no title

    title_text = title_elem.get_text(strip=True)

    # Use the source URL as the GUID
    guid_text = source_url

    # Create new item element
    new_item = ET.Element('item')

    # Add title
    title = ET.SubElement(new_item, 'title')
    title.text = title_text

    # Add link (same as GUID for permalink)
    link = ET.SubElement(new_item, 'link')
    link.text = guid_text

    # Extract date (optional) for RSS metadata
    date_elem = gallery_item.select_one('.gallery_item-date')
    date = date_elem.get('datetime') if date_elem else None
    if date:
        pubDate = ET.SubElement(new_item, 'pubDate')
        pubDate.text = date

    # Add GUID
    guid = ET.SubElement(new_item, 'guid')
    guid.text = guid_text
    guid.set('isPermaLink', 'true')  # Since we're using the URL as the GUID

    # Build content HTML preserving the original order
    content_parts = []

    # Description that appears before images
    desc_before = gallery_item.select_one('.gallery_item-description')
    if desc_before and desc_before.parent == gallery_item and desc_before.find_previous_sibling() == title_elem:
        content_parts.append(f'<div class="description">{desc_before.decode_contents()}</div>')

    # Process main gallery content
    content_container = gallery_item.select_one('.gallery_item-content')
    if content_container:
        # Main focused image
        main_image = content_container.select_one('.gallery_item-focused_image')
        if main_image:
            image_url = main_image.get('src', '')
            content_parts.append(f'<img src="{image_url}" alt="{title_text}" class="main-image">')

        # Metadata (resolution, colors, date)
        meta_section = content_container.select_one('.gallery_item-meta')
        if meta_section:
            meta_parts = []

            # Date in the displayed format
            date_display = meta_section.select_one('.gallery_item-date')
            if date_display:
                date_text = date_display.get_text(strip=True)
                meta_parts.append(f'<span class="date">{date_text}</span>')

            # Resolution
            resolution_elem = meta_section.select_one('.gallery_item-resolution')
            if resolution_elem:
                resolution = resolution_elem.get_text(strip=True).replace('×', '&times;')
                meta_parts.append(f'<span class="resolution">{resolution}</span>')

            # Colors count
            colors_elem = meta_section.select_one('.gallery_item-colors')
            if colors_elem:
                colors_count = colors_elem.get_text(strip=True)
                meta_parts.append(f'<span class="colors">{colors_count}</span>')

            if meta_parts:
                content_parts.append(f'<div class="metadata">{" | ".join(meta_parts)}</div>')

        # Alternative images
        alt_images = content_container.select_one('.gallery_item-alts')
        if alt_images:
            alt_imgs_html = []
            for alt_img in alt_images.select('.gallery_item-alt img'):
                alt_src = alt_img.get('src', '')
                if alt_src:
                    alt_imgs_html.append(f'<img src="{alt_src}" class="alt-image">')

            if alt_imgs_html:
                content_parts.append(f'<div class="alt-images">{"".join(alt_imgs_html)}</div>')

    # Description that appears after images (if not already processed)
    desc_after = gallery_item.select_one('.gallery_item-description')
    if desc_after and not (desc_before and desc_after == desc_before):
        content_parts.append(f'<div class="description">{desc_after.decode_contents()}</div>')

    # Set the content
    description = ET.SubElement(new_item, 'description')
    description.text = "".join(content_parts)

    return new_item, guid_text


def update_feed(html_content: str, feed_path: str, source_url: str) -> int:
    """
    Update the RSS feed with new items from the HTML content.

    Args:
        html_content: HTML content to parse
        feed_path: Path to the RSS feed file
        source_url: URL where the HTML content was fetched from

    Returns:
        Number of new items added to the feed
    """
    # Parse the HTML content
    soup = BeautifulSoup(html_content, 'html.parser')

    # Load or create the feed
    root, channel, existing_guids, tree = load_or_create_feed(feed_path)

    # Find all gallery items
    gallery_items = soup.select('.gallery_item-lightbox')
    new_items_added = 0

    for item in gallery_items:
        new_item, guid_text = create_feed_item(item, source_url)
        if new_item is None or guid_text is None:
            continue

        # Check if this item already exists in the feed
        if guid_text in existing_guids:
            print(f"Skipping duplicate item: {new_item.find('title').text}")
            continue

        # Item is new, so add it to the feed
        new_items_added += 1
        # Add the new item to the channel (prepend it as the first item)
        channel.insert(4, new_item)  # Insert after title, link, description, docs
        existing_guids.add(guid_text)

    # Save the updated feed only if new items were added
    if new_items_added > 0:
        if tree is None:
            tree = ET.ElementTree(root)
        tree.write(feed_path, encoding='utf-8', xml_declaration=True)
        print(f"RSS feed updated with {new_items_added} new item(s) and saved to {feed_path}")
    else:
        print("No new items found. RSS feed remains unchanged.")

    return new_items_added


def main():
    feed_path = 'feed.rss'
    # Get the unstaged diff
    diff_content = get_unstaged_diff()

    # Extract gallery links
    gallery_links = extract_gallery_links(diff_content)

    if gallery_links:
        print(f"Found {len(gallery_links)} new gallery items")
        total_items_added = 0
        for url in gallery_links:
            html_content = fetch_html_content(url)
            if html_content:
                items_added = update_feed(html_content, feed_path, url)
                total_items_added += items_added
        print(f"Total new items added to feed: {total_items_added}")
    else:
        print("No new gallery items found")


if __name__ == "__main__":
    main()