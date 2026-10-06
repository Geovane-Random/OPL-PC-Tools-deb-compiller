#!/usr/bin/env python3
import os
import shutil
import subprocess
import sys
from pathlib import Path


def clean_dragged_path(raw_path: str) -> str:
    """Remove aspas simples/duplas e espaços extras do arrastar-e-soltar do terminal."""
    path_str = raw_path.strip()
    if (path_str.startswith("'") and path_str.endswith("'")) or (
        path_str.startswith('"') and path_str.endswith('"')
    ):
        path_str = path_str[1:-1]
    return path_str.strip()


def sanitize_pkg_name(raw_name: str) -> str:
    """Gera um nome válido para o campo Package no DEBIAN/control

    (apenas minúsculas, números, hífens e pontos).
    """
    cleaned = raw_name.lower().replace("_", "-").replace(" ", "-")
    return "".join(c for c in cleaned if c.isalnum() or c in ("-", "."))


def build_deb_package(target_dir: str):
    """Analisa a pasta do app e gera um pacote .deb preservando o nome original."""
    cleaned_dir = clean_dragged_path(target_dir)
    target_path = Path(cleaned_dir).resolve()

    if not target_path.exists() or not target_path.is_dir():
        print(
            f"\n❌ Erro: O diretório '{target_path}' não existe ou não é uma pasta válida."
        )
        return False

    # Guardar o nome exato da pasta original para dar nome ao arquivo .deb
    original_folder_name = target_path.name

    app_title = None
    exec_path = None
    icon_path = None
    version = "1.0.0"
    categories = "Utility;Game;"

    print(f"\n🔍 Analisando pasta: {target_path}")

    # 1. Procurar por arquivo .desktop existente para extrair metadados (se houver)
    for file in target_path.glob("*.desktop"):
        try:
            with open(file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.startswith("Name="):
                        app_title = line.split("=", 1)[1].strip()
                    elif line.startswith("Categories="):
                        categories = line.split("=", 1)[1].strip()
        except Exception as e:
            print(f"⚠️ Aviso ao ler .desktop existente: {e}")

    # 2. Identificar o script shell (.sh) principal de inicialização
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
            print(f"⚠️ Erro ao analisar o script {file.name}: {e}")

    # Fallback: Se não encontrou script com LD_LIBRARY_PATH, pega qualquer .sh principal
    if not exec_path:
        for file in target_path.glob("*.sh"):
            if not file.name.startswith(("make-", "install")):
                exec_path = file.resolve()
                if not app_title:
                    app_title = file.stem.replace("-", " ").replace("_", " ").title()
                break

    if not exec_path:
        print("❌ Nenhum script de inicialização (.sh) válido foi encontrado.")
        return False

    if not app_title:
        app_title = original_folder_name.replace("-", " ").replace("_", " ").title()

    # 3. Localizar o arquivo de ícone (.png ou .svg)
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

    # Sanitizar o nome do pacote para a estrutura do DPKG
    pkg_name = sanitize_pkg_name(original_folder_name)

    # Definir caminhos de montagem da estrutura do .deb
    build_root = Path.cwd() / f"deb_build_{pkg_name}"
    if build_root.exists():
        shutil.rmtree(build_root)

    opt_app_dir = build_root / "opt" / pkg_name
    bin_dir = build_root / "usr" / "local" / "bin"
    apps_dir = build_root / "usr" / "share" / "applications"
    debian_dir = build_root / "DEBIAN"

    try:
        # Criar a árvore de diretórios
        opt_app_dir.mkdir(parents=True, exist_ok=True)
        bin_dir.mkdir(parents=True, exist_ok=True)
        apps_dir.mkdir(parents=True, exist_ok=True)
        debian_dir.mkdir(parents=True, exist_ok=True)

        # Copiar arquivos do aplicativo para /opt/<pkg_name>
        print(f"📦 Copiando arquivos para a estrutura DEB...")
        for item in target_path.iterdir():
            dest = opt_app_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)

        # Definir o executável dentro de /opt
        target_exec_in_opt = opt_app_dir / exec_path.name
        os.chmod(target_exec_in_opt, 0o755)

        # Criar link simbólico do binário para /usr/local/bin
        bin_symlink = bin_dir / pkg_name
        rel_target = Path("/opt") / pkg_name / exec_path.name
        os.symlink(rel_target, bin_symlink)

        # Determinar caminho final do ícone
        opt_icon_path = ""
        if icon_path:
            rel_icon = icon_path.relative_to(target_path)
            opt_icon_path = str(Path("/opt") / pkg_name / rel_icon)

        # Criar o atalho .desktop em /usr/share/applications/
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

        # Criar o arquivo DEBIAN/control
        control_content = f"""Package: {pkg_name}
Version: {version}
Section: utils
Priority: optional
Architecture: amd64
Maintainer: Local Installer <installer@local>
Description: {app_title} - Empacotado automaticamente
 Package gerado a partir de {original_folder_name}.
"""
        with open(debian_dir / "control", "w", encoding="utf-8") as f:
            f.write(control_content)

        # Nome final mantendo a nomenclatura exata da pasta original
        output_deb_filename = f"{original_folder_name}_amd64.deb"
        output_deb_path = Path.cwd() / output_deb_filename

        print(f"⚙️  Gerando pacote com dpkg-deb...")
        result = subprocess.run(
            ["dpkg-deb", "--build", str(build_root), str(output_deb_path)],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            print(f"❌ Erro ao empacotar DEB: {result.stderr}")
            return False

        print("\n✅ Pacote .DEB gerado com sucesso!")
        print(f"   📌 Nome da App: {app_title}")
        print(f"   📄 Arquivo Gerado: {output_deb_path}")
        print(f"\n💡 Para instalar, você pode rodar:")
        print(f"   sudo dpkg -i \"{output_deb_path}\"")

        return True

    except Exception as e:
        print(f"❌ Erro inesperado durante a criação do .deb: {e}")
        return False

    finally:
        # Limpeza da pasta temporária de compilação
        if build_root.exists():
            shutil.rmtree(build_root)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        folder_input = sys.argv[1]
    else:
        folder_input = input("📂 Arraste a pasta para este terminal e pressione Enter: ")

    build_deb_package(folder_input)
