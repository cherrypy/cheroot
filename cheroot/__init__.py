try:
	import pkg_resources
	__version__ = pkg_resources.get_distribution('cheroot').version
except (ImportError, pkg_resources.DistributionNotFound):
	__version__ = 'unknown'
