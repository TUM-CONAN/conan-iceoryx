from conan import ConanFile
from conan.tools.cmake import CMake, CMakeToolchain, cmake_layout, CMakeDeps
from conan.tools.gnu import PkgConfigDeps
from conan.tools.scm import Git
from conan.tools.files import save, patch, rmdir, mkdir, rename, copy, get, replace_in_file, collect_libs
from conan.tools.build import check_min_cppstd, stdcpp_library
from conan.tools.system.package_manager import Apt
from conans.errors import ConanInvalidConfiguration

import os
import textwrap

required_conan_version = ">=1.55.0"


class IceoryxConan(ConanFile):
    name = "iceoryx"
    version = "2.0.2"

    license = "Apache-2.0"
    homepage = "https://iceoryx.io/"
    url = "https://github.com/conan-io/conan-center-index"
    description = "Eclipse iceoryx - true zero-copy inter-process-communication"
    topics = ("Shared Memory", "IPC", "ROS", "Middleware")

    settings = "os", "arch", "compiler", "build_type"

    options = {
        "shared": [True, False],
        "fPIC": [True, False],
        "toml_config": [True, False],
    }
    default_options = {
        "shared": False,
        "fPIC": True,
        "toml_config": True,
    }

    exports_sources = ("CMakeLists.txt", "patches/*")

    def system_requirements(self):
        if self.settings.os == "Linux":
            pack_names = []
            pack_names.append("libacl1-dev")

            Apt(self).install(pack_names)

    def config_options(self):
        if self.settings.os == "Windows":
            del self.options.fPIC

    def configure(self):
        if self.options.shared:
            del self.options.fPIC

    def requirements(self):
        if self.options.toml_config:
            self.requires("cpptoml/0.1.1")
        if self.settings.os == "Linux":
            self.requires("acl/2.3.1")

    def build_requirements(self):
        self.tool_requires("cmake/3.25.3")

    def validate(self):
        compiler = self.settings.compiler
        version = str(self.settings.compiler.version)

        if compiler.get_safe("cppstd"):
            check_min_cppstd(self, 14)

    def source(self):
        get(self, **self.conan_data["sources"][self.version], strip_root=True, destination=self.source_folder)

    def _patch_sources(self):
        for p in self.conan_data.get("patches", {}).get(self.version, []):
            patch(self, **p)
        # Honor fPIC option
        iceoryx_utils = "iceoryx_hoofs"
        for cmake_file in [
                os.path.join("iceoryx_binding_c", "CMakeLists.txt"),
                os.path.join("iceoryx_posh", "CMakeLists.txt"),
                os.path.join(iceoryx_utils, "CMakeLists.txt")
        ]:
            replace_in_file(self, os.path.join(self.source_folder, cmake_file), "POSITION_INDEPENDENT_CODE ON", "")




    def generate(self):
        tc = CMakeToolchain(self)

        def add_cmake_option(option, value):
            var_name = "{}".format(option).upper()
            value_str = "{}".format(value)
            var_value = "ON" if value_str == 'True' else "OFF" if value_str == 'False' else value_str
            tc.variables[var_name] = var_value

        for option, value in self.options.items():
            add_cmake_option(option, value)

        tc.cache_variables["TOML_CONFIG"] = self.options.toml_config
        tc.cache_variables["DOWNLOAD_TOML_LIB"] = False

        tc.generate()

        deps = CMakeDeps(self)
        deps.generate()

        deps = PkgConfigDeps(self)
        deps.generate()

    def layout(self):
        cmake_layout(self)

    def build(self):
        self._patch_sources()
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        cmake = CMake(self)
        cmake.install()
        copy(self, "LICENSE", src=self.source_folder, dst=os.path.join(self.package_folder, "licenses"))
        rmdir(self, os.path.join(self.package_folder, "share"))
        rmdir(self, os.path.join(self.package_folder, "lib", "cmake"))
        if self.options.toml_config:
            mkdir(self, os.path.join(self.package_folder, "res"))
            rename(self, os.path.join(self.package_folder, "etc", "roudi_config_example.toml"),
                         os.path.join(self.package_folder, "res", "roudi_config.toml"))
        rmdir(self, os.path.join(self.package_folder, "etc"))
        # bring to default package structure
        include_paths = ["iceoryx_binding_c", "iceoryx_hoofs", "iceoryx_posh", "iceoryx_versions.hpp"]
        for include_path in include_paths:
            rename(self, 
                os.path.join(self.package_folder, "include", "iceoryx", "v{}".format(self.version), include_path),
                os.path.join(self.package_folder, "include", include_path))

        # TODO: to remove in conan v2 once cmake_find_package* generators removed
        self._create_cmake_module_alias_targets(
            os.path.join(self.package_folder, self._module_file_rel_path),
            {v["target"]: "iceoryx::{}".format(k)
             for k, v in self._iceoryx_components["2.0.0"].items()})

    @property
    def _iceoryx_components(self):

        def pthread():
            return ["pthread"] if self.settings.os in ["Linux", "FreeBSD"] else []

        def rt():
            return ["rt"] if self.settings.os in ["Linux", "FreeBSD"] else []

        def atomic():
            return ["atomic"] if self.settings.os == "Linux" else []

        def acl():
            return ["acl::acl"] if self.settings.os == "Linux" else []

        def cpptoml():
            return ["cpptoml::cpptoml"] if self.options.toml_config else []

        def libcxx():
            libcxx = stdcpp_library(self)
            return [libcxx] if libcxx and not self.options.shared else []

        return {
            "2.0.0": {
                "iceoryx_platform": {
                    "target": "iceoryx_hoofs::iceoryx_platform",
                    "system_libs": pthread() + rt(),
                    "requires": [],
                    "includeDir": False
                },
                "iceoryx_hoofs": {
                    "target": "iceoryx_hoofs::iceoryx_hoofs",
                    "system_libs": pthread() + rt() + atomic(),
                    "requires": ["iceoryx_platform"] + acl(),
                    "includeDir": True
                },
                "iceoryx_posh": {
                    "target": "iceoryx_posh::iceoryx_posh",
                    "system_libs": pthread() + rt(),
                    "requires": ["iceoryx_hoofs"],
                    "includeDir": True
                },
                "iceoryx_posh_roudi": {
                    "target": "iceoryx_posh::iceoryx_posh_roudi",
                    "system_libs": pthread(),
                    "requires": ["iceoryx_hoofs", "iceoryx_posh"] + cpptoml(),
                    "includeDir": False
                },
                "iceoryx_posh_gateway": {
                    "target": "iceoryx_posh::iceoryx_posh_gateway",
                    "system_libs": pthread(),
                    "requires": ["iceoryx_hoofs", "iceoryx_posh"],
                    "includeDir": False
                },
                "iceoryx_posh_config": {
                    "target": "iceoryx_posh::iceoryx_posh_config",
                    "system_libs": pthread(),
                    "requires": ["iceoryx_posh_roudi", "iceoryx_hoofs", "iceoryx_posh"],
                    "includeDir": False
                },
                "iceoryx_binding_c": {
                    "target": "iceoryx_binding_c::iceoryx_binding_c",
                    "system_libs": pthread() + libcxx(),
                    "requires": ["iceoryx_hoofs", "iceoryx_posh"],
                    "includeDir": True
                }
            }
        }

    def _create_cmake_module_alias_targets(self, module_file, targets):
        content = ""
        for alias, aliased in targets.items():
            content += textwrap.dedent("""\
                if(TARGET {aliased} AND NOT TARGET {alias})
                    add_library({alias} INTERFACE IMPORTED)
                    set_property(TARGET {alias} PROPERTY INTERFACE_LINK_LIBRARIES {aliased})
                endif()
            """.format(alias=alias, aliased=aliased))
        save(self, module_file, content)

    @property
    def _module_file_rel_path(self):
        return os.path.join("lib", "cmake", "conan-official-{}-targets.cmake".format(self.name))

    def package_info(self):
        # FIXME: We should provide 3 CMake config files:
        #        iceoryx_utilsConfig.cmake, iceoryx_poshConfig.cmake and iceoryx_binding_cConfig.cmake
        #        It's not possible yet, see https://github.com/conan-io/conan/issues/9000
        self.cpp_info.set_property("cmake_file_name", "iceoryx")

        def _register_components(components):
            for lib_name, values in components.items():
                cmake_target = values.get("target", [])
                system_libs = values.get("system_libs", [])
                requires = values.get("requires", [])
                self.cpp_info.components[lib_name].set_property("cmake_target_name", cmake_target)
                self.cpp_info.components[lib_name].libs = [lib_name]
                self.cpp_info.components[lib_name].system_libs = system_libs
                self.cpp_info.components[lib_name].requires = requires
                # TODO: to remove in conan v2 once cmake_find_package* generators removed
                self.cpp_info.components[lib_name].build_modules["cmake_find_package"] = [self._module_file_rel_path]
                self.cpp_info.components[lib_name].build_modules["cmake_find_package_multi"] = [
                    self._module_file_rel_path
                ]

        _register_components(self._iceoryx_components["2.0.0"])

        bin_path = os.path.join(self.package_folder, "bin")
        self.output.info("Appending PATH environment variable: {}".format(bin_path))
        self.env_info.PATH.append(bin_path)

