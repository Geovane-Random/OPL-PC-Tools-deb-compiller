#!/usr/bin/env python3
import os
import shutil
import subprocess
import sys
from pathlib import Path


def clean_dragged_path(raw_path: str) -> str:
    """Remove single/double quotes and extra spaces added by drag-and-drop in the terminal."""
    path_str = raw_path.strip()
    if (path_str.startswith("'") and path_str.endswith("'")) or (
        path_str.startswith('"') and path_str.endswith('"')
    ):
        path_str = path_str[1:-1]
    return path_str.strip()


def sanitize_pkg_name(raw_name: str) -> str:
    """Generate a valid name for the Package field in DEBIAN/control

    (lowercase letters, numbers, hyphens, and periods only).
    """
    cleaned = raw_name.lower().replace("_", "-").replace(" ", "-")
    return "".join(c for c in cleaned if c.isalnum() or c in ("-", "."))


def build_deb_package(target_dir: str):
    """Analyze the app folder and generate a .deb package preserving the original name."""
    cleaned_dir = clean_dragged_path(target_dir)
    target_path = Path(cleaned_dir).resolve()

    if not target_path.exists() or not target_path.is_dir():
        print(
            f"\n❌ Error: Directory '{target_path}' does not exist or is not a valid folder."
        )
        return False

    # Store the exact name of the original folder to name the .deb file
    original_folder_name = target_path.name

    app_title = None
    exec_path = None
    icon_path = None
    version = "1.0.0"
    categories = "Utility;Game;"

    print(f"\n🔍 Analyzing folder: {target_path}")

    # 1. Look for an existing .desktop file to extract metadata (if present)
    for file in target_path.glob("*.desktop"):
        try:
            with open(file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.startswith("Name="):
                        app_title = line.split("=", 1)[1].strip()
                    elif line.startswith("Categories="):
                        categories = line.split("=", 1)[1].strip()
        except Exception as e:
            print(f"⚠️ Warning reading existing .desktop file: {e}")

    # 2. Identify the main startup shell script (.sh)
    for file in target_path.glob("*.sh"):
        filename = file.name.lower()
        if filename.startswith("make-") or filename.startswith("install"):
            continue

        try:
            with open(file, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                if (
                    "LD_LIBRARY_PATH" in content
                    or "bin/" in content
                    or "dirname" in content
                ):
                    exec_path = file.resolve()
                    if not app_title:
                        app_title = file.stem.replace("-", " ").replace("_", " ").title()
                    break
        except Exception as e:
            print(f"⚠️ Error analyzing script {file.name}: {e}")

    # Fallback: If no script with LD_LIBRARY_PATH was found, pick any main .sh
    if not exec_path:
        for file in target_path.glob("*.sh"):
            if not file.name.startswith(("make-", "install")):
                exec_path = file.resolve()
                if not app_title:
                    app_title = file.stem.replace("-", " ").replace("_", " ").title()
                break

    if not exec_path:
        print("❌ No valid startup shell script (.sh) was found.")
        return False

    if not app_title:
        app_title = original_folder_name.replace("-", " ").replace("_", " ").title()

    # 3. Locate icon file (.png or .svg)
    for root, _, files in os.walk(target_path):
        for file in files:
            if file.lower().endswith((".png", ".svg", ".xpm")):
                full_icon_path = Path(root) / file
                if (
                    "icon" in file.lower()
                    or "images" in str(full_icon_path)
                    or not icon_path
                ):
                    icon_path = full_icon_path.resolve()
                    if "icon" in file.lower():
                        break

    # Sanitize package name for DPKG structure
    pkg_name = sanitize_pkg_name(original_folder_name)

    # Define build paths for .deb structure
    build_root = Path.cwd() / f"deb_build_{pkg_name}"
    if build_root.exists():
        shutil.rmtree(build_root)

    opt_app_dir = build_root / "opt" / pkg_name
    bin_dir = build_root / "usr" / "local" / "bin"
    apps_dir = build_root / "usr" / "share" / "applications"
    debian_dir = build_root / "DEBIAN"

    try:
        # Create directory tree
        opt_app_dir.mkdir(parents=True, exist_ok=True)
        bin_dir.mkdir(parents=True, exist_ok=True)
        apps_dir.mkdir(parents=True, exist_ok=True)
        debian_dir.mkdir(parents=True, exist_ok=True)

        # Copy application files to /opt/<pkg_name>
        print("📦 Copying files to DEB structure...")
        for item in target_path.iterdir():
            dest = opt_app_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)

        # Set executable inside /opt
        target_exec_in_opt = opt_app_dir / exec_path.name
        os.chmod(target_exec_in_opt, 0o755)

        # Create symlink from binary to /usr/local/bin
        bin_symlink = bin_dir / pkg_name
        rel_target = Path("/opt") / pkg_name / exec_path.name
        os.symlink(rel_target, bin_symlink)

        # Determine final icon path
        opt_icon_path = ""
        if icon_path:
            rel_icon = icon_path.relative_to(target_path)
            opt_icon_path = str(Path("/opt") / pkg_name / rel_icon)

        # Create .desktop shortcut in /usr/share/applications/
        desktop_content = f"""[Desktop Entry]
Name={app_title}
Exec=/usr/local/bin/{pkg_name}
Path=/opt/{pkg_name}
Icon={opt_icon_path}
Terminal=false
Type=Application
Categories={categories}
StartupNotify=true
"""
        desktop_file_path = apps_dir / f"{pkg_name}.desktop"
        with open(desktop_file_path, "w", encoding="utf-8") as f:
            f.write(desktop_content)
        os.chmod(desktop_file_path, 0o755)

        # Create DEBIAN/control file
        control_content = f"""Package: {pkg_name}
Version: {version}
Section: utils
Priority: optional
Architecture: amd64
Maintainer: Local Installer <installer@local>
Description: {app_title} - Automatically packaged
 Package generated from {original_folder_name}.
"""
        with open(debian_dir / "control", "w", encoding="utf-8") as f:
            f.write(control_content)

        # Final output filename retaining original folder name
        output_deb_filename = f"{original_folder_name}_amd64.deb"
        output_deb_path = Path.cwd() / output_deb_filename

        print("⚙️️  Building package with dpkg-deb...")
        result = subprocess.run(
            ["dpkg-deb", "--build", str(build_root), str(output_deb_path)],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            print(f"❌ Error packaging DEB: {result.stderr}")
            return False

        print("\n✅ .DEB package generated successfully!")
        print(f"   📌 App Name: {app_title}")
        print(f"   📄 Generated File: {output_deb_path}")
        print("\n💡 To install, you can run:")
        print(f'   sudo dpkg -i "{output_deb_path}"')

        return True

    except Exception as e:
        print(f"❌ Unexpected error during .deb creation: {e}")
        return False

    finally:
        # Cleanup temporary build directory
        if build_root.exists():
            shutil.rmtree(build_root)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        folder_input = sys.argv[1]
    else:
        folder_input = input("📂 Drag the folder into this terminal and press Enter: ")

    build_deb_package(folder_input)
