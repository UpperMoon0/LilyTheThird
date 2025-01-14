from actions import file_action
from actions import browser_action


def execute_command(action):
    if action is not None:
        action = action.lower()

        if 'download' in action:
            if 'extract' in action or 'unsort' in action:
                file_action.unsort_download()
            elif 'sort' in action or 'organize' in action:
                file_action.sort_download()
        elif 'browse' in action or 'search' in action:
            keyword = action.split(' ', 1)[1]
            browser_action.browse(keyword)

