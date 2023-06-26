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

import fixtures
import subprocess
import yaml

from kubernetes import client as kube_client
from kubernetes import config as kube_config
from oslo_log import log as logging
from oslo_serialization import base64
from oslo_utils import uuidutils
from tempest.lib.common.utils import data_utils
from tempest.lib import decorators
from tempest.lib import exceptions
import testtools

from magnum_tempest_plugin.common import config
from magnum_tempest_plugin.common import datagen
from magnum_tempest_plugin.common import utils
from magnum_tempest_plugin.tests.api import base


HEADERS = {'OpenStack-API-Version': 'container-infra latest',
           'Accept': 'application/json',
           'Content-Type': 'application/json'}


class ClusterTest(base.BaseTempestTest):

    """Tests for cluster CRUD."""

    LOG = logging.getLogger(__name__)

    LOG.setLevel(logging.DEBUG)

    delete_template = False

    def __init__(self, *args, **kwargs):
        super(ClusterTest, self).__init__(*args, **kwargs)
        self.clusters = []

    def setUp(self):
        super(ClusterTest, self).setUp()

        try:
            (self.creds, self.keypair) = self.get_credentials_with_keypair(
                type_of_creds='default'
            )
            (self.cluster_template_client,
             self.keypairs_client) = self.get_clients_with_existing_creds(
                creds=self.creds,
                type_of_creds='default',
                request_type='cluster_template'
            )
            (self.cluster_client, _) = self.get_clients_with_existing_creds(
                creds=self.creds,
                type_of_creds='default',
                request_type='cluster'
            )
            (self.cert_client, _) = self.get_clients_with_existing_creds(
                creds=self.creds,
                type_of_creds='default',
                request_type='cert'
            )

            if config.Config.cluster_template_id:
                _, self.cluster_template = self.cluster_template_client.\
                    get_cluster_template(config.Config.cluster_template_id)
            else:
                model = datagen.valid_cluster_template()
                _, self.cluster_template = self._create_cluster_template(model)
                self.delete_template = True
        except Exception:
            raise

        # NOTE (dimtruck) by default tempest sets timeout to 20 mins.
        # We need more time.
        test_timeout = 3600
        self.useFixture(fixtures.Timeout(test_timeout, gentle=True))

    def tearDown(self):
        try:
            cluster_list = self.clusters[:]
            for cluster_id in cluster_list:
                self._delete_cluster(cluster_id)
                self.clusters.remove(cluster_id)

            if self.delete_template:
                self._delete_cluster_template(self.cluster_template.uuid)

            if config.Config.keypair_name:
                self.keypairs_client.delete_keypair(config.Config.keypair_name)
        finally:
            super(ClusterTest, self).tearDown()

    def _create_cluster_template(self, cm_model):
        self.LOG.debug('We will create a clustertemplate for %s', cm_model)
        resp, model = self.cluster_template_client.post_cluster_template(
            cm_model)
        return resp, model

    def _delete_cluster_template(self, cm_id):
        self.LOG.debug('We will delete a clustertemplate for %s', cm_id)
        resp, model = self.cluster_template_client.delete_cluster_template(
            cm_id)
        return resp, model

    def _create_cluster(self, cluster_model):
        self.LOG.debug('We will create cluster for %s', cluster_model)
        resp, model = self.cluster_client.post_cluster(cluster_model)
        self.LOG.debug('Response: %s', resp)
        self.assertEqual(202, resp.status)
        self.assertIsNotNone(model.uuid)
        self.assertTrue(uuidutils.is_uuid_like(model.uuid))
        self.clusters.append(model.uuid)
        self.cluster_uuid = model.uuid
        if config.Config.copy_logs:
            self.addCleanup(self.copy_logs_handler(
                lambda: list(
                    [self._get_cluster_by_id(model.uuid)[1].master_addresses,
                     self._get_cluster_by_id(model.uuid)[1].node_addresses]),
                self.cluster_template.coe,
                self.keypair))

        timeout = config.Config.cluster_creation_timeout * 60
        self.cluster_client.wait_for_created_cluster(model.uuid,
                                                     delete_on_error=False,
                                                     timeout=timeout)
        return resp, model

    def _delete_cluster(self, cluster_id):
        self.LOG.debug('We will delete a cluster for %s', cluster_id)
        resp, model = self.cluster_client.delete_cluster(cluster_id)
        self.assertEqual(204, resp.status)

        self.cluster_client.wait_for_cluster_to_delete(cluster_id)

        self.assertRaises(exceptions.NotFound, self.cert_client.get_cert,
                          cluster_id, headers=HEADERS)
        return resp, model

    def _get_cluster_by_id(self, cluster_id):
        resp, model = self.cluster_client.get_cluster(cluster_id)
        return resp, model

    # def test_create_delete_cluster(self):

    #     model = datagen.valid_cluster_template()
    #     _, cluster_template = self._create_cluster_template(model)
    #     gen_model = datagen.valid_cluster_data(
    #         cluster_template_id=cluster_template.uuid, node_count=1)
    #     _, cluster_model = self._create_cluster(gen_model)

    #     self._delete_cluster(cluster_model.uuid)
    #     self.clusters.remove(cluster_model.uuid)

    #     self._delete_cluster_template(cluster_template.uuid)

    # (dimtruck) Combining all these tests in one because
    # they time out on the gate (2 hours not enough)
    @testtools.testcase.attr('positive')
    @testtools.testcase.attr('slow')
    @decorators.idempotent_id('44158a8c-a856-11e9-9382-00224d6b7bc1')
    def test_create_list_sign_delete_clusters(self):

        gen_model = datagen.valid_cluster_data(
            cluster_template_id=self.cluster_template.uuid, node_count=1)

        # test cluster create
        _, cluster_model = self._create_cluster(gen_model)
        self.assertNotIn('status', cluster_model)

        # test cluster list
        resp, cluster_list_model = self.cluster_client.list_clusters()
        self.assertEqual(200, resp.status)
        self.assertGreater(len(cluster_list_model.clusters), 0)
        self.assertIn(
            cluster_model.uuid, list([x['uuid']
                                      for x in cluster_list_model.clusters]))

        # test ca show
        resp, cert_model = self.cert_client.get_cert(
            cluster_model.uuid, headers=HEADERS)
        self.LOG.debug("cert resp: %s", resp)
        self.assertEqual(200, resp.status)
        self.assertEqual(cert_model.cluster_uuid, cluster_model.uuid)
        self.assertIsNotNone(cert_model.pem)
        self.assertIn('-----BEGIN CERTIFICATE-----', cert_model.pem)
        self.assertIn('-----END CERTIFICATE-----', cert_model.pem)

        # test ca sign
        csr_sample = """-----BEGIN CERTIFICATE REQUEST-----
MIIByjCCATMCAQAwgYkxCzAJBgNVBAYTAlVTMRMwEQYDVQQIEwpDYWxpZm9ybmlh
MRYwFAYDVQQHEw1Nb3VudGFpbiBWaWV3MRMwEQYDVQQKEwpHb29nbGUgSW5jMR8w
HQYDVQQLExZJbmZvcm1hdGlvbiBUZWNobm9sb2d5MRcwFQYDVQQDEw53d3cuZ29v
Z2xlLmNvbTCBnzANBgkqhkiG9w0BAQEFAAOBjQAwgYkCgYEApZtYJCHJ4VpVXHfV
IlstQTlO4qC03hjX+ZkPyvdYd1Q4+qbAeTwXmCUKYHThVRd5aXSqlPzyIBwieMZr
WFlRQddZ1IzXAlVRDWwAo60KecqeAXnnUK+5fXoTI/UgWshre8tJ+x/TMHaQKR/J
cIWPhqaQhsJuzZbvAdGA80BLxdMCAwEAAaAAMA0GCSqGSIb3DQEBBQUAA4GBAIhl
4PvFq+e7ipARgI5ZM+GZx6mpCz44DTo0JkwfRDf+BtrsaC0q68eTf2XhYOsq4fkH
Q0uA0aVog3f5iJxCa3Hp5gxbJQ6zV6kJ0TEsuaaOhEko9sdpCoPOnRBm2i/XRD2D
6iNh8f8z0ShGsFqjDgFHyF3o+lUyj+UC6H1QW7bn
-----END CERTIFICATE REQUEST-----
"""

        cert_data_model = datagen.cert_data(cluster_model.uuid,
                                            csr_data=csr_sample)
        resp, cert_model = self.cert_client.post_cert(cert_data_model,
                                                      headers=HEADERS)
        self.LOG.debug("cert resp: %s", resp)
        self.assertEqual(201, resp.status)
        self.assertEqual(cert_model.cluster_uuid, cluster_model.uuid)
        self.assertIsNotNone(cert_model.pem)
        self.assertIn('-----BEGIN CERTIFICATE-----', cert_model.pem)
        self.assertIn('-----END CERTIFICATE-----', cert_model.pem)

        # test cluster delete
        self._delete_cluster(cluster_model.uuid)
        self.clusters.remove(cluster_model.uuid)

    @testtools.testcase.attr('negative')
    @decorators.idempotent_id('11c293da-a857-11e9-9382-00224d6b7bc1')
    def test_create_cluster_for_nonexisting_cluster_template(self):
        cm_id = 'this-does-not-exist'
        gen_model = datagen.valid_cluster_data(cluster_template_id=cm_id)
        self.assertRaises(
            exceptions.BadRequest,
            self.cluster_client.post_cluster, gen_model)

    @testtools.testcase.attr('positive')
    @testtools.testcase.attr('slow')
    @decorators.idempotent_id('262eb132-a857-11e9-9382-00224d6b7bc1')
    def test_create_cluster_with_zero_nodes(self):
        gen_model = datagen.valid_cluster_data(
            cluster_template_id=self.cluster_template.uuid, node_count=0)

        # test cluster create
        _, cluster_model = self._create_cluster(gen_model)
        self.assertNotIn('status', cluster_model)

        # test cluster delete
        self._delete_cluster(cluster_model.uuid)
        self.clusters.remove(cluster_model.uuid)

    @testtools.testcase.attr('negative')
    @decorators.idempotent_id('29c6c5f0-a857-11e9-9382-00224d6b7bc1')
    def test_create_cluster_with_zero_masters(self):
        uuid = self.cluster_template.uuid
        gen_model = datagen.valid_cluster_data(cluster_template_id=uuid,
                                               master_count=0)
        self.assertRaises(
            exceptions.BadRequest,
            self.cluster_client.post_cluster, gen_model)

    @testtools.testcase.attr('negative')
    @decorators.idempotent_id('2cf16528-a857-11e9-9382-00224d6b7bc1')
    def test_create_cluster_with_nonexisting_flavor(self):
        gen_model = \
            datagen.cluster_template_data_with_valid_keypair_image_flavor()
        resp, cluster_template = self._create_cluster_template(gen_model)
        self.assertEqual(201, resp.status)
        self.assertIsNotNone(cluster_template.uuid)

        uuid = cluster_template.uuid
        gen_model = datagen.valid_cluster_data(cluster_template_id=uuid)
        gen_model.flavor_id = 'aaa'
        self.assertRaises(exceptions.BadRequest,
                          self.cluster_client.post_cluster, gen_model)

        resp, _ = self._delete_cluster_template(cluster_template.uuid)
        self.assertEqual(204, resp.status)

    @testtools.testcase.attr('negative')
    @decorators.idempotent_id('33bd0416-a857-11e9-9382-00224d6b7bc1')
    def test_update_cluster_for_nonexisting_cluster(self):
        patch_model = datagen.cluster_name_patch_data()

        self.assertRaises(
            exceptions.NotFound,
            self.cluster_client.patch_cluster, 'fooo', patch_model)

    @testtools.testcase.attr('negative')
    @decorators.idempotent_id('376c45ea-a857-11e9-9382-00224d6b7bc1')
    def test_delete_cluster_for_nonexisting_cluster(self):
        self.assertRaises(
            exceptions.NotFound,
            self.cluster_client.delete_cluster, data_utils.rand_uuid())

    @testtools.testcase.attr('positive')
    @decorators.idempotent_id('f4c33092-7eeb-43d7-826e-bba16fd61e28')
    def test_create_cluster_and_get_kubeconfig(self):

        gen_model = datagen.valid_cluster_data(
            cluster_template_id=self.cluster_template.uuid, node_count=2)

        # test cluster create
        _, cluster_model = self._create_cluster(gen_model)
        self.assertNotIn('status', cluster_model)

        _, cluster_model = self._get_cluster_by_id(cluster_model.uuid)

        # template kubeconfig

        # generate csr and private key
        csr_sample = utils.generate_csr_and_key()

        # get CA cert
        _, ca = self.cert_client.get_cert(cluster_model.uuid,
                                          headers=HEADERS)
        # sign CSR
        cert_data_model = datagen.cert_data(cluster_model.uuid,
                                            csr_data=csr_sample['csr'])

        resp, cert_model = self.cert_client.post_cert(cert_data_model,
                                                      headers=HEADERS)
        cfg = """
---
apiVersion: v1
clusters:
  - cluster:
      certificate-authority-data: {ca}
      server: {api_address}
    name: {name}
contexts:
  - context:
      cluster: {name}
      user: admin
    name: default
current-context: default
kind: Config
preferences: {{}}
users:
  - name: admin
    user:
      client-certificate-data: {cert}
      client-key-data: {key}
""".format(name=cluster_model.name,
           api_address=cluster_model.api_address,
           key=base64.encode_as_text(csr_sample['key']),
           cert=base64.encode_as_text(cert_model.pem),
           ca=base64.encode_as_text(ca.pem))

        cfg = yaml.safe_load(cfg)

        self.LOG.info("Generated kubeconfig: %s", cfg)

        kube_config.load_kube_config_from_dict(cfg)

        v1 = kube_client.CoreV1Api()

        resp = v1.list_node(pretty="true")

        self.LOG.info("LIST NODES: %s", resp)

        self.LOG.info("Running sonobuoy on created cluster...")

        # TODO(johng): add config for sonoboy path,
        # and install in magnum devstack pluigin
        process = subprocess.Popen(
            ["run-sonobuoy", str(cfg)], stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT)
        with process.stdout:
            utils.log_subprocess_output(process.stdout, self.LOG)
        exitcode = process.wait()

        if exitcode != 0:
            self.LOG.error("sonobuoy process exited with status %s", exitcode)
        self.assertEqual(0, exitcode)

        # test cluster delete
        self._delete_cluster(cluster_model.uuid)
        self.clusters.remove(cluster_model.uuid)
