# import os

# for key, value in os.environ.items():
#     print(f"{key}: {value}")

lines = "".join(['def load_data(filepath):\n', '    """\n', '    Load data from the specified file path\n', '    \n', '    Args:\n', '        filepath (str): Path to the data file\n', '        \n', '    Returns:\n', '        dict: Loaded data\n', '    """\n', '    print(f"Loading data from {filepath}")\n', '    # Simulate loading data\n', '    return {"status": "success", "items": [1, 2, 3, 4, 5]}\n'])[:-1].split('\n')
print(len(lines))
numbered_content = '\n'.join(f"{i+1:3d} | {line}" for i, line in enumerate(lines))
print(numbered_content)