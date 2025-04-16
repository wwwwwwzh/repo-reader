### Commands Ran
- python -m app.remote_tree_builder build https://github.com/wwwwwwzh/demo-repo.git main.py:__main__   --db-uri postgresql://codeuser:<code_password>@159.223.132.83:5432/code   --verbose
- python -m app.remote_tree_builder build https://github.com/wwwwwwzh/D2RF-mini  run_nerf.py:__main__   --db-uri postgresql://codeuser:<code_password>@159.223.132.83:5432/code   --verbose

v0.0.2 
- python -m app.remote_tree_builder build https://github.com/wwwwwwzh/demo-repo.git main.py:__main__   --db-uri postgresql://codeuser:<code_password>@159.223.132.83:5432/code   --verbose --reuse_registry False False False -f
- python -m app.remote_tree_builder build https://github.com/wwwwwwzh/demo-repo.git main.py:__main__   --db-uri postgresql://codeuser:<code_password>@159.223.132.83:5432/code   --verbose --reuse_registry True True False