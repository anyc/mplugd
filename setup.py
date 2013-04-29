from setuptools import setup, find_packages
import glob, os

def get_datafiles():
	l = [("share/mplugd", ["mplugd.conf.example"])]
	prefix = "share/"
	for root, dirs, files in os.walk("mplugd/examples/action.d/"):
		f = []
		for filename in files:
			fullpath = os.path.join(root, filename)
			f.append(fullpath)
		l.append((prefix+root, f))
	return l

setup(
	name="mplugd",
	version="0.1",
	packages=['mplugd', 'mplugd.plugins'],
	data_files=get_datafiles(),
	entry_points = {
		"console_scripts": [ "mplugd=mplugd.mplugd:main", ],
	}
)