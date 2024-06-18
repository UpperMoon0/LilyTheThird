import os
import shutil


def sort_download():
    download_dir = os.path.expanduser('~/Downloads')  # Path to the Download directory
    file_types = {
        'image': ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.webp'],
        'video': ['.mp4', '.mkv', '.flv', '.avi', '.mov', '.wmv'],
        'doc': ['.txt', '.doc', '.docx', '.pdf', '.odt'],
        'music': ['.mp3', '.wav', '.flac', '.m4a', '.wma', '.aac', '.ogg', '.opus'],
        'slide': ['.ppt', '.pptx', '.odp'],
        'spreadsheet': ['.xls', '.xlsx', '.ods', '.csv'],
        'zip': ['.zip', '.rar', '.tar', '.gz', '.bz2'],
        'other': []
    }

    for filename in os.listdir(download_dir):
        file_path = os.path.join(download_dir, filename)
        if os.path.isfile(file_path):
            file_ext = os.path.splitext(filename)[1]
            for type, extensions in file_types.items():
                if file_ext in extensions:
                    type_dir = os.path.join(download_dir, type)
                    if not os.path.exists(type_dir):
                        os.mkdir(type_dir)
                    shutil.move(file_path, type_dir)
                    break
            else:
                other_dir = os.path.join(download_dir, 'other')
                if not os.path.exists(other_dir):
                    os.mkdir(other_dir)
                shutil.move(file_path, other_dir)


def unsort_download():
    download_dir = os.path.expanduser('~/Downloads')  # Path to the Download directory
    file_types = ['image', 'video', 'doc', 'music', 'slide', 'spreadsheet', 'zip', 'other']

    for file_type in file_types:
        type_dir = os.path.join(download_dir, file_type)
        if os.path.exists(type_dir):
            for filename in os.listdir(type_dir):
                file_path = os.path.join(type_dir, filename)
                if os.path.isfile(file_path):
                    shutil.move(file_path, download_dir)
