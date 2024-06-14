import file_action
import browser_action


def execute_command(action):
    str.lower(action)

    if action is not None:
        print(action)

        if 'download' in action:
            if 'extract' in action:
                file_action.unsort_download()
            elif 'sort' or 'organize' in action:
                file_action.sort_download()
        elif 'browse' in action:
            keyword = action.split(' ')[1]
            browser_action.browse(keyword)
