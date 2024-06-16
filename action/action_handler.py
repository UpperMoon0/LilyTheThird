from action import file_action
from action import browser_action


def execute_command(action):
    if action is not None:
        str.lower(action)
        print(action)

        if 'download' in action:
            if 'extract' or 'unsort' in action:
                file_action.unsort_download()
            elif 'sort' or 'organize' in action:
                file_action.sort_download()
        elif 'browse' in action:
            keyword = action[action.find('browse') + len('browse'):]
            browser_action.browse(keyword)
        elif 'add' in action:
            if 'alarm' or 'reminder' in action:
                # get time from string
                time = action[action.find('add') + len('add'):]
