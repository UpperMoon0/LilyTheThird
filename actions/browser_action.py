import webbrowser


def browse(keyword):
    # open the browser and search for the keyword
    url = "https://www.google.com/search?q=" + keyword
    webbrowser.open(url)
