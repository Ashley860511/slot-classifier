try:
    from .analysis.export_analysis import main
except ImportError:
    from analysis.export_analysis import main


if __name__ == "__main__":
    main()

