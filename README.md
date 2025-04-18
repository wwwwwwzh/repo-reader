### Version History
0.0.1

0.0.2
- builder side upgrade. see demo-repo 0.0.2, added recognition for object instantiation and object method calls.
0.0.3
- builder side upgrade. see demo-repo 0.0.3, added recognition for call from objects passed into a function. eg Foo(a: Boo): a.call()

0.0.4
- various patches on builder side. 
- clicking code now finds component or new function.
- robust scrolling behavior

0.0.5
- patched call recognition defunct from batch segment analysis; reimplemented batch segment analysis (shape of motion has 500 functions) 
- basic rag indexing and qa system
- fucntion search update: if too many functions, just use full name, original was to append short description
- defaulting all groq to llama-3.1-8b-instant (128k context) and meta-llama/llama-4-scout-17b-16e-instruct

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
- python -m app.remote_tree_builder build https://github.com/wwwwwwzh/D2RF-mini run_nerf.py:__main__   --db-uri postgresql://codeuser:<code_password>@159.223.132.83:5432/code   --verbose --reuse_registry True True False -f

v0.0.4
- python -m app.remote_tree_builder build https://github.com/wwwwwwzh/demo-repo.git main.py:main utils/helpers.py:generate_report --db-uri postgresql://codeuser:<code_password>@159.223.132.83:5432/code --verbose --reuse_registry False False False -f
- python -m app.remote_tree_builder build https://github.com/wwwwwwzh/demo-repo.git main.py:main --db-uri postgresql://codeuser:<code_password>@159.223.132.83:5432/code --verbose --reuse_registry True True False -f
- python -m app.remote_tree_builder build https://github.com/vye16/shape-of-motion run_training.py:main run_rendering.py:main preproc/process_custom.py:main scripts/evaluate_iphone.py:__main__  --db-uri postgresql://codeuser:<code_password>@159.223.132.83:5432/code   --verbose --reuse_registry False False False -f
- python -m app.remote_tree_builder build https://github.com/vye16/shape-of-motion run_training.py:main run_rendering.py:main preproc/process_custom.py:main scripts/evaluate_iphone.py:__main__   --db-uri postgresql://codeuser:<code_password>@159.223.132.83:5432/code --verbose --reuse_registry True True True -f --batch-size 10

v0.0.5
- python -m app.remote_tree_builder build https://github.com/wwwwwwzh/demo-repo.git main.py:main --db-uri postgresql://codeuser:<code_password>@159.223.132.83:5432/code --verbose --reuse_registry True True True True -f
- python -m app.utils.repository_qa 3dc413bf54ba3f74e587e8b45b23172b08ffd67e1dd38dc376d3c8b8cc5163d4 "What's the main fuction"
- python -m app.remote_tree_builder build https://github.com/wwwwwwzh/D2RF-mini run_nerf.py:__main__ --db-uri postgresql://codeuser:<code_password>@159.223.132.83:5432/code --verbose --reuse_registry True True True True -f
- python -m app.utils.repository_qa 95eb1fea142ab66445473488472dcefae8aa4f5c185724c85192e00af3af37f2 "How are renderings generated"
- python -m app.remote_tree_builder build https://github.com/vye16/shape-of-motion run_training.py:main run_rendering.py:main preproc/process_custom.py:main scripts/evaluate_iphone.py:__main__ --db-uri postgresql://codeuser:<code_password>@159.223.132.83:5432/code --verbose --reuse_registry True True True True -f
- python -m app.utils.repository_qa 23d13f5d589dca921d0c8752ed4430f483d676d43db5c172ba4df8f9a6b907bf "How are cameras loaded"
```
Cameras are loaded in different ways depending on the camera type.

For the "droid_recon" camera type, cameras are loaded using the `load_cameras` function (Function1), which takes a file path, height (H), and width (W) as inputs. This function loads camera data from a file, including transformation matrices, intrinsic matrices, and timestamps as tensors.

For the "megasam" camera type, camera data is loaded directly in the `CasualDataset.__init__` function (Function2). It loads camera poses and intrinsics from a file and computes the inverse transformation matrices.

In the `iPhoneDataset.__init__` function (Function4), cameras are loaded in three different ways depending on the camera type: "original", "refined", or "monst3r". 

- For the "original" camera type, camera intrinsics and poses are loaded from JSON files.
- For the "refined" camera type, camera intrinsics and poses are loaded using the `get_colmap_camera_params` function.
- For the "monst3r" camera type, camera intrinsics are loaded from a text file and poses are loaded from a text file.

The camera loading process involves computing the inverse transformation matrices and scaling the intrinsics. The loaded camera data is then used to initialize the dataset object. 

The actual loading of camera data into the dataset objects happens in their respective `__init__` functions, i.e., `CasualDataset.__init__` and `iPhoneDataset.__init__`. 

In the case of rendering, camera poses are interpolated and used to render a scene. The rendering is handled by the `populate_render_tab` function (Functions3 and 5), which populates a render tab with various GUI elements and functionality. This function handles camera pose interpolation and rendering. 

Here are some key functions and their roles in loading cameras:

- `load_cameras` (Function1): Loads camera data from a file.
- `CasualDataset.__init__` (Function2): Initializes a CasualDataset object and loads camera data.
- `iPhoneDataset.__init__` (Function4): Initializes an iPhoneDataset object and loads camera data. 
- `populate_render_tab` (Functions3 and 5): Populates a render tab and handles camera pose interpolation and rendering.

RELEVANT FUNCTIONS:
- flow3d.data.casual_dataset.load_cameras (Score: 0.3748)
- flow3d.data.casual_dataset.CasualDataset.__init__ (Score: 0.3172)
- flow3d.vis.render_panel.populate_render_tab (Score: 0.2393)
- flow3d.data.iphone_dataset.iPhoneDataset.__init__ (Score: 0.2372)
- flow3d.vis.render_panel.populate_render_tab (Score: 0.2313)
```