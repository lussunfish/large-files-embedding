def test_package_importable() -> None:
    import large_files_embedding as pkg

    assert pkg.__name__ == "large_files_embedding"
