from setuptools import Extension, setup
from Cython.Build import cythonize

extensions = [
    Extension("engine.order_book", ["engine/order_book.pyx"]),
    Extension("engine.matching_core", ["engine/matching_core.pyx"]),
]

setup(
    name="chronosmatch",
    version="0.2.0",
    description="Educational Cython-based paper trading and matching engine",
    ext_modules=cythonize(
        extensions,
        compiler_directives={"language_level": "3"},
    ),
)
