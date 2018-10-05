#! /usr/bin/env python
"""Cheroot package setuptools installer."""

import setuptools


try:
    from setuptools.config import read_configuration
except ImportError:
    """This is a shim for setuptools<30.3."""
    import io

    try:
        from configparser import ConfigParser, NoSectionError
    except ImportError:
        from ConfigParser import ConfigParser, NoSectionError
        ConfigParser.read_file = ConfigParser.readfp

    def read_configuration(filepath):
        """Read metadata and options from setup.cfg located at filepath."""
        cfg = ConfigParser()
        with io.open(filepath, encoding='utf-8') as f:
            cfg.read_file(f)
        def maybe_read_files(d):
            d = d.strip()
            if not d.startswith('file:'):
                return d
            descs = []
            for fname in map(str.strip, d[5:].split(',')):
                with io.open(fname, encoding='utf-8') as f:
                    descs.append(f.read())
            return ''.join(descs)
        cfg_val_to_list = lambda _: list(filter(bool, map(str.strip, _.strip().splitlines())))
        cfg_val_to_dict = lambda _: dict(map(lambda l: list(map(str.strip, l.split('=', 1))), filter(bool, map(str.strip, _.strip().splitlines()))))
        cfg_val_to_primitive = lambda _: json.loads(_.strip().lower())
        md = dict(cfg.items('metadata'))
        for list_key in 'classifiers', 'keywords':
            try:
                md[list_key] = cfg_val_to_list(md[list_key])
            except KeyError:
                pass
        try:
            md['long_description'] = maybe_read_files(md['long_description'])
        except KeyError:
            pass
        opt = dict(cfg.items('options'))
        try:
            opt['zip_safe'] = cfg_val_to_primitive(opt['zip_safe'])
        except KeyError:
            pass
        for list_key in 'scripts', 'install_requires', 'setup_requires':
            try:
                opt[list_key] = cfg_val_to_list(opt[list_key])
            except KeyError:
                pass
        try:
            opt['package_dir'] = cfg_val_to_dict(opt['package_dir'])
        except KeyError:
            pass
        opt_package_data = dict(cfg.items('options.package_data'))
        try:
            if not opt_package_data.get('', '').strip():
                opt_package_data[''] = opt_package_data['*']
                del opt_package_data['*']
        except KeyError:
            pass
        try:
            opt_extras_require = dict(cfg.items('options.extras_require'))
            opt['extras_require'] = {}
            for k, v in opt_extras_require.items():
                opt['extras_require'][k] = cfg_val_to_list(v)
        except NoSectionError:
            pass
        opt['package_data'] = {}
        for k, v in opt_package_data.items():
            opt['package_data'][k] = cfg_val_to_list(v)
        cur_pkgs = opt.get('packages', '').strip()
        if '\n' in cur_pkgs:
            opt['packages'] = cfg_val_to_list(opt['packages'])
        elif cur_pkgs.startswith('find:'):
            opt_packages_find = dict(cfg.items('options.packages.find'))
            opt['packages'] = find_packages(**opt_packages_find)
        return {'metadata': md, 'options': opt}

def to_bool(val):
    truthy_vals = (
        'True', 'true',
        'On', 'on',
        'Yes', 'yes',
        1, True,
    )
    return val in truthy_vals


setup_params = {}
declarative_setup_params = read_configuration('setup.cfg')

setup_params = dict(setup_params, **declarative_setup_params['metadata'])
setup_params = dict(setup_params, **declarative_setup_params['options'])

# Hot fix 'use_scm_version' option type to bool
setup_params['use_scm_version'] = to_bool(setup_params['use_scm_version'])


__name__ == '__main__' and setuptools.setup(**setup_params)
