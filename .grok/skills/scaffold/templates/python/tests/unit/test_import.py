def test_package_importable() -> None:
    import {{PYTHON_PACKAGE}} as pkg

    assert pkg.__name__ == "{{PYTHON_PACKAGE}}"
