"""Image handling and resolution for Craigslist posting."""

from pathlib import Path
from typing import List


def resolve_existing_images(image_names: List[str]) -> List[str]:
    """Resolve image paths from common locations; log misses; return existing file paths as strings."""
    resolved: List[str] = []
    missing: List[str] = []
    base_dir = Path(__file__).parent.parent
    cwd = Path.cwd()
    home = Path.home()
    common_dirs = [
        base_dir,
        base_dir / "images",
        cwd,
        cwd / "images",
        home / "Downloads",
        home / "Pictures",
    ]

    for name in image_names:
        name = str(name).strip()
        if not name:
            continue
        # Absolute or relative path direct hit
        p = Path(name)
        if p.exists() and p.is_file():
            resolved.append(str(p.resolve()))
            continue

        # Try common folders
        matched = False
        for folder in common_dirs:
            candidate = folder / name
            if candidate.exists() and candidate.is_file():
                resolved.append(str(candidate.resolve()))
                matched = True
                break
        if not matched:
            missing.append(name)

    if missing:
        print(f"[images] Missing files (skipped): {', '.join(missing)}")
    if resolved:
        print(f"[images] Resolved files: {', '.join(resolved)}")
    return resolved


class ImageManager:
    """Manages image file resolution and validation for posting."""
    
    def __init__(self, image_names: List[str]):
        self.image_names = image_names
        self._resolved_images: List[str] = []
        
    def resolve_images(self) -> List[str]:
        """Resolve image file paths from various common locations."""
        if not self._resolved_images:
            self._resolved_images = resolve_existing_images(self.image_names)
        return self._resolved_images
        
    def has_images(self) -> bool:
        """Check if any valid image files were found."""
        resolved = self.resolve_images()
        return len(resolved) > 0
        
    def log_image_status(self) -> None:
        """Log the current image resolution status."""
        resolved = self.resolve_images()
        if not resolved:
            print("[images] No image files found to upload (looked in CWD, script dir, and script/images). Skipping upload phase.")
        else:
            print(f"[images] Found {len(resolved)} images ready for upload.")
