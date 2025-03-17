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

def copy_pull_request_template(src, dest):
    src_template = os.path.join(src, 'PULL_REQUEST_TEMPLATE.md')
    dest_template = os.path.join(dest, 'PULL_REQUEST_TEMPLATE.md')
    if os.path.exists(src_template) and not os.path.exists(dest_template):
        shutil.copy(src_template, dest_template)
        print(f"Copied PULL_REQUEST_TEMPLATE.md to {dest}")

def main():
    src_dir = os.path.dirname(os.path.abspath(__file__))
    dest_dir = os.path.dirname(src_dir)

    copy_gitignore(src_dir, dest_dir)
    create_bom_folder(dest_dir)
    copy_pull_request_template(src_dir, dest_dir)

if __name__ == "__main__":
    main()