from setuptools import find_packages, setup

setup(
    name='wheeltec_explore', version='0.1.0', packages=find_packages(exclude=['test']),
    data_files=[('share/ament_index/resource_index/packages',['resource/wheeltec_explore']),
                ('share/wheeltec_explore',['package.xml','README.md'])],
    install_requires=['setuptools'], zip_safe=True,
    maintainer='Kanye Shen', maintainer_email='189834982+KANYE-Shen@users.noreply.github.com',
    description='Bounded occupancy-grid frontier exploration for WHEELTEC and Nav2',
    license='LicenseRef-Proprietary',
    entry_points={'console_scripts':['explore = wheeltec_explore.node:main']},
)