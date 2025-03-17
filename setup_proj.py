import os
import shutil
import argparse

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

def move_jobsets(src, dest):
    src_jobsets = os.path.join(src, 'Jobsets')
    dest_jobsets = os.path.join(dest, 'Jobsets')
    if os.path.exists(src_jobsets):
        if not os.path.exists(dest_jobsets):
            os.makedirs(dest_jobsets)
        for item in os.listdir(src_jobsets):
            src_item = os.path.join(src_jobsets, item)
            dest_item = os.path.join(dest_jobsets, item)
            if os.path.isfile(src_item) and not os.path.exists(dest_item):
                shutil.move(src_item, dest_item)
                print(f"Moved {item} to {dest_jobsets}")

def main():
    parser = argparse.ArgumentParser(description="Copy project setup files to the destination directory.")
    parser.add_argument('dest_dir', nargs='?', default=None, help='The destination directory to copy files to')
    args = parser.parse_args()

    src_dir = os.path.dirname(os.path.abspath(__file__))
    dest_dir = args.dest_dir if args.dest_dir else os.path.dirname(src_dir)

    copy_gitignore(src_dir, dest_dir)
    create_bom_folder(dest_dir)
    copy_pull_request_template(src_dir, dest_dir)
    move_jobsets(src_dir, dest_dir)

if __name__ == "__main__":
    main()