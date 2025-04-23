import importlib.util
import os

def load_modules_from_folder(folder_path):
    modules = {}
    for filename in os.listdir(folder_path):
        if filename.endswith('.py') and filename != '__init__.py':
            module_name = filename[:-3]
            module_path = os.path.join(folder_path, filename)
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if hasattr(module, 'menu_text') and callable(getattr(module, 'menu_text', None)):
                module.menu_text = module.menu_text()
            if hasattr(module, 'file_types') and callable(getattr(module, 'file_types', None)):
                module.file_types = module.file_types()
            if hasattr(module, 'analysis_name') and callable(getattr(module, 'analysis_name', None)):
                module.analysis_name = module.analysis_name()
            if hasattr(module, 'analysis_types') and callable(getattr(module, 'analysis_types', None)):
                module.analysis_types = module.analysis_types()
            modules[module_name] = module
    return modules
