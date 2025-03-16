import os
import shutil

def copy_gitignore(src, dest):
    src_gitignore = os.path.join(src, '.gitignore')
    dest_gitignore = os.path.join(dest, '.gitignore')
    if os.path.exists(src_gitignore):
        shutil.copy(src_gitignore, dest_gitignore)
        print(f"Copied .gitignore to {dest}")

def create_bom_folder(dest):
    bom_folder = os.path.join(dest, 'bom')
    if not os.path.exists(bom_folder):
        os.makedirs(bom_folder)
        print(f"Created bom/ folder at {dest}")

def create_pretty_and_lib_files(dest):
    kicad_pro_file = None
    for file in os.listdir(dest):
        if file.endswith('.kicad_pro'):
            kicad_pro_file = file
            break

    if kicad_pro_file:
        file_name = os.path.splitext(kicad_pro_file)[0]
        pretty_folder = os.path.join(dest, f"{file_name}.pretty")
        lib_file = os.path.join(dest, f"{file_name}.lib")

        if not os.path.exists(pretty_folder):
            os.makedirs(pretty_folder)
            print(f"Created {file_name}.pretty folder at {dest}")

        if not os.path.exists(lib_file):
            with open(lib_file, 'w') as f:
                f.write(f"# {file_name} library file\n")
            print(f"Created {file_name}.lib file at {dest}")

def main():
    src_dir = '/Users/lakshaygupta/Documents/LHR/KiCAD-Bild'
    dest_dir = '/path/to/outer/directory'  # Change this to the actual outer directory path

    copy_gitignore(src_dir, dest_dir)
    create_bom_folder(dest_dir)
    create_pretty_and_lib_files(dest_dir)

if __name__ == "__main__":
    main()