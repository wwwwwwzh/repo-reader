### Version History
0.0.1

0.0.2
- see demo-repo 0.0.2, added recognition for object instantiation and object method calls.
0.0.3
- see demo-repo 0.0.3, added recognition for call from objects passed into a function. eg Foo(a: Boo): a.call()

### Commands Ran
- python -m app.remote_tree_builder build https://github.com/wwwwwwzh/demo-repo.git main.py:__main__   --db-uri postgresql://codeuser:<code_password>@159.223.132.83:5432/code   --verbose
- python -m app.remote_tree_builder build https://github.com/wwwwwwzh/D2RF-mini  run_nerf.py:__main__   --db-uri postgresql://codeuser:<code_password>@159.223.132.83:5432/code   --verbose

v0.0.2 
- python -m app.remote_tree_builder build https://github.com/wwwwwwzh/demo-repo.git main.py:__main__   --db-uri postgresql://codeuser:<code_password>@159.223.132.83:5432/code   --verbose --reuse_registry False False False -f
- python -m app.remote_tree_builder build https://github.com/wwwwwwzh/demo-repo.git main.py:__main__   --db-uri postgresql://codeuser:<code_password>@159.223.132.83:5432/code   --verbose --reuse_registry True True False

v0.0.3
- python -m app.remote_tree_builder build https://github.com/wwwwwwzh/demo-repo.git main.py:__main__   --db-uri postgresql://codeuser:<code_password>@159.223.132.83:5432/code   --verbose --reuse_registry False False False -f
- python -m app.remote_tree_builder build https://github.com/wwwwwwzh/demo-repo.git main.py:__main__   --db-uri postgresql://codeuser:<code_password>@159.223.132.83:5432/code   --verbose --reuse_registry True True True -f
- python -m app.remote_tree_builder build https://github.com/wwwwwwzh/D2RF-mini run_nerf.py:__main__   --db-uri postgresql://codeuser:<code_password>@159.223.132.83:5432/code   --verbose --reuse_registry False False False -f
- python -m app.remote_tree_builder build https://github.com/wwwwwwzh/D2RF-mini run_nerf.py:__main__   --db-uri postgresql://codeuser:<code_password>@159.223.132.83:5432/code   --verbose --reuse_registry True True True -f