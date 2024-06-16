import win32com.client

def add_alarm(time):
    TASK_TRIGGER_DAILY = 2
    TASK_CREATE_OR_UPDATE = 6
    TASK_ACTION_EXEC = 0
    TASK_LOGON_INTERACTIVE_TOKEN = 3

    scheduler = win32com.client.Dispatch('Schedule.Service')
    scheduler.Connect()

    root_folder = scheduler.GetFolder('\\')

    task_def = scheduler.NewTask(0)

    # Create a daily trigger
    trigger = task_def.Triggers.Create(TASK_TRIGGER_DAILY)
    trigger.StartBoundary = time.strftime('%Y-%m-%dT%H:%M:%S')
    trigger.DaysInterval = 1

    # Set the action to execute
    action = task_def.Actions.Create(TASK_ACTION_EXEC)
    action.Path = 'C:\\Windows\\System32\\SoundRecorder.exe'
    action.Arguments = '/FILE %UserProfile%\\Music\\Recordings\\Recording.m4a /DURATION 0000:00:30'

    # Set the principal logon type
    principal = task_def.Principal
    principal.LogonType = TASK_LOGON_INTERACTIVE_TOKEN

    # Register the task (create or update)
    root_folder.RegisterTaskDefinition(
        'My Alarm',  # Task name
        task_def,
        TASK_CREATE_OR_UPDATE,
        '',  # No user
        '',  # No password
        principal.LogonType
    )

# Usage:
import datetime
alarm_time = datetime.datetime.now() + datetime.timedelta(minutes=1)  # Set alarm for 1 minute from now
add_alarm(alarm_time)