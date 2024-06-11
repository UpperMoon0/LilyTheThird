from command import file_command


def execute_command(action):
    str.lower(action)

    if action is not None:
        print(action)

        if 'download' in action:
            if 'extract' in action:
                file_command.unsort_download()
            elif 'sort' or 'organize' in action:
                file_command.sort_download()
