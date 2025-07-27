def paginate_output(text):
    """
    Displays text page by page in the console.
    """
    lines = text.split("\n")
    page_length = 10
    for i in range(0, len(lines), page_length):
        page = lines[i:i + page_length]
        print('\n'.join(page))
        if i + page_length < len(lines):
            try:
                input("Press Enter to continue...")
            except EOFError:
                break
