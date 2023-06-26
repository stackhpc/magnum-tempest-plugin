# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from oslo_config import cfg
from tempest import config  # noqa


service_available_group = cfg.OptGroup(name="service_available",
                                       title="Available OpenStack Services")

ServiceAvailableGroup = [
    cfg.BoolOpt("magnum",
                default=True,
                help="Whether or not magnum is expected to be available"),
]

magnum_group = cfg.OptGroup(name="magnum", title="Magnum Options")

MagnumGroup = [
    cfg.StrOpt("docker_storage_driver",
               help="Docker storage driver. Supported: devicemapper, overlay"),
    cfg.StrOpt("image_id",
               default="fedora-coreos-latest",
               help="Image id to be used for ClusterTemplate."),
    cfg.StrOpt("nic_id",
               default="public",
               help="NIC id."),
    cfg.StrOpt("keypair_name",
               default="magnum-test",
               help="Keypair name to use to log into nova instances, the "
                    "keypair is created automatically if not exist."),
    cfg.StrOpt("flavor_id",
               default="ds2G",
               help="Flavor id to use for ClusterTemplate."),
    cfg.StrOpt("magnum_url",
               help="Bypass URL for Magnum to skip service catalog lookup"),
    cfg.StrOpt("master_flavor_id",
               default="ds2G",
               help="Master flavor id to use for ClusterTemplate."),
    cfg.StrOpt("csr_location",
               default="/opt/stack/new/magnum/default.csr",
               deprecated_for_removal=True,
               help="CSR location for certificates. This option is no "
               "longer used for anything."),
    cfg.StrOpt("dns_nameserver",
               default="8.8.8.8",
               help="DNS nameserver to use for ClusterTemplate."),
    cfg.BoolOpt("copy_logs",
                default=True,
                help="Specify whether to copy nova server logs on failure."),
    cfg.StrOpt("coe",
               default="kubernetes",
               help="Container Orchestration Engine"),
    cfg.StrOpt("network_driver",
               help="Network Driver"),
    cfg.StrOpt("cluster_template_id",
               help="UUID of cluster template used for the test."),
    cfg.IntOpt("cluster_creation_timeout",
               default=30,
               help="Timeout(in minutes) to wait for the cluster creation "
                    "finished."),
    cfg.BoolOpt("master-lb-enabled",
                default=True,
                help="Indicates whether created Clusters should have a load \
                      balancer for master nodes or not."),
    cfg.DictOpt("labels",
                default={}),
]
