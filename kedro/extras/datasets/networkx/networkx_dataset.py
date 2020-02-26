# Copyright 2020 QuantumBlack Visual Analytics Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
# OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND
# NONINFRINGEMENT. IN NO EVENT WILL THE LICENSOR OR OTHER CONTRIBUTORS
# BE LIABLE FOR ANY CLAIM, DAMAGES, OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF, OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#
# The QuantumBlack Visual Analytics Limited ("QuantumBlack") name and logo
# (either separately or in combination, "QuantumBlack Trademarks") are
# trademarks of QuantumBlack. The License does not grant you any right or
# license to the QuantumBlack Trademarks. You may not use the QuantumBlack
# Trademarks or any confusingly similar mark as a trademark for your product,
#     or use the QuantumBlack Trademarks in any other manner that might cause
# confusion in the marketplace, including but not limited to in advertising,
# on websites, or on software.
#
# See the License for the specific language governing permissions and
# limitations under the License.


"""``NetworkXDataSet`` loads and saves graphs to a JSON file using an underlying
filesystem (e.g.: local, S3, GCS). ``NetworkX`` is used to create JSON data.
"""

import json
from copy import deepcopy
from pathlib import PurePosixPath
from typing import Any, Dict

import fsspec
import networkx

from kedro.io.core import (
    AbstractVersionedDataSet,
    Version,
    get_filepath_str,
    get_protocol_and_path,
)


class NetworkXDataSet(AbstractVersionedDataSet):
    """``NetworkXDataSet`` loads and saves graphs to a JSON file using an
    underlying filesystem (e.g.: local, S3, GCS). ``NetworkX`` is used to
    create JSON data.
    See https://networkx.github.io/documentation/stable/tutorial.html for details.

    Example:
    ::

        >>> from kedro.extras.datasets.networkx import NetworkXDataSet
        >>> import networkx as nx
        >>> graph = nx.complete_graph(100)
        >>> graph_dataset = NetworkXDataSet(filepath="test.json")
        >>> graph_dataset.save(graph)
        >>> reloaded = graph_dataset.load()
        >>> assert nx.is_isomorphic(graph, reloaded)

    """

    DEFAULT_LOAD_ARGS = {}  # type: Dict[str, Any]
    DEFAULT_SAVE_ARGS = {}  # type: Dict[str, Any]

    # pylint: disable=too-many-arguments
    def __init__(
        self,
        filepath: str,
        load_args: Dict[str, Any] = None,
        save_args: Dict[str, Any] = None,
        version: Version = None,
        credentials: Dict[str, Any] = None,
        fs_args: Dict[str, Any] = None,
        layer: str = None,
    ) -> None:
        """Creates a new instance of ``NetworkXDataSet``.

        Args:
            filepath: The path to the NetworkX graph JSON file.
            load_args: Arguments passed on to ```networkx.node_link_graph``.
                See the details in
                https://networkx.github.io/documentation/networkx-1.9.1/reference/generated/networkx.readwrite.json_graph.node_link_graph.html
            save_args: Arguments passed on to ```networkx.node_link_data``.
                See the details in
                https://networkx.github.io/documentation/networkx-1.9.1/reference/generated/networkx.readwrite.json_graph.node_link_data.html
            version: If specified, should be an instance of
                ``kedro.io.core.Version``. If its ``load`` attribute is
                None, the latest version will be loaded. If its ``save``
                attribute is None, save version will be autogenerated.
            credentials: Credentials required to get access to the underlying filesystem.
                E.g. for ``GCSFileSystem`` it should look like `{"token": None}`.
            fs_args: Extra arguments to pass into underlying filesystem class.
                E.g. for ``GCSFileSystem`` class: `{"project": "my-project", ...}`
            layer: The data layer according to the data engineering convention:
                https://kedro.readthedocs.io/en/stable/06_resources/01_faq.html#what-is-data-engineering-convention
        """
        _fs_args = deepcopy(fs_args) or {}
        _credentials = deepcopy(credentials) or {}

        protocol, path = get_protocol_and_path(filepath, version)

        self._layer = layer
        self._protocol = protocol
        self._fs = fsspec.filesystem(self._protocol, **_credentials, **_fs_args)

        super().__init__(
            filepath=PurePosixPath(path),
            version=version,
            exists_function=self._fs.exists,
            glob_function=self._fs.glob,
        )

        # Handle default load and save arguments
        self._load_args = deepcopy(self.DEFAULT_LOAD_ARGS)
        if load_args is not None:
            self._load_args.update(load_args)
        self._save_args = deepcopy(self.DEFAULT_SAVE_ARGS)
        if save_args is not None:
            self._save_args.update(save_args)

    def _load(self) -> networkx.Graph:
        load_path = get_filepath_str(self._get_load_path(), self._protocol)
        with self._fs.open(load_path, mode="r") as fs_file:
            json_payload = json.load(fs_file)

        return networkx.node_link_graph(json_payload, **self._load_args)

    def _save(self, data: networkx.Graph) -> None:
        save_path = get_filepath_str(self._get_save_path(), self._protocol)

        json_graph = networkx.node_link_data(data, **self._save_args)
        with self._fs.open(save_path, mode="w") as fs_file:
            json.dump(json_graph, fs_file)

        self.invalidate_cache()

    def _exists(self) -> bool:
        load_path = get_filepath_str(self._get_load_path(), self._protocol)

        return self._fs.exists(load_path)

    def _describe(self) -> Dict[str, Any]:
        return dict(
            filepath=self._filepath,
            protocol=self._protocol,
            load_args=self._load_args,
            save_args=self._save_args,
            version=self._version,
            layer=self._layer,
        )

    def _release(self) -> None:
        self.invalidate_cache()

    def invalidate_cache(self) -> None:
        """Invalidate underlying filesystem caches."""
        filepath = get_filepath_str(self._filepath, self._protocol)
        self._fs.invalidate_cache(filepath)
