try:
	import pkg_resources
	__version__ = pkg_resources.get_distribution('cheroot').version
except ImportError:
	__version__ = 'unknown'
