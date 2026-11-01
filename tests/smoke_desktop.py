"""Compatible entry point for the current full-image workbench acceptance."""
from smoke_workbench import main

if __name__ == '__main__':
    from multiprocessing import freeze_support
    freeze_support()
    main()