from setuptools import Extension, setup
from Cython.Build import cythonize

extensions = [
    Extension(
        name="engine.order_book",
        sources=["engine/order_book.pyx"],
    )
]

setup(
    name="chronosmatch",
    ext_modules=cythonize(
        extensions,
        compiler_directives={"language_level": "3"},
    ),
)
