#!/usr/bin/python

# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.


DOCUMENTATION = '''
---
module: swarm_service
author: "Dario Zanzico (@dariko)"
short_description: docker swarm service
description: |
  Manage docker services. Allows live altering of already defined services
  (see examples)
options:
  name:
    required: true
    description:
    - Service name
  image:
    required: true
    description:
    - Service image path and tag.
      Maps docker service IMAGE parameter.
  state:
    required: true
    description:
    - Service state.
    choices:
    - present
    - absent
  args:
    required: false
    default: []
    description:
    - List comprised of the command and the arguments to be run inside
      the container
  constraints:
    required: false
    default: []
    description:
    - List of the service constraints.
      Maps docker service --constraint option.
  labels:
    required: false
    description:
    - List of the service labels.
      Maps docker service --label option.
  container_labels:
    required: false
    description:
    - List of the service containers labels.
      Maps docker service --container-label option.
    default: []
  endpoint_mode:
    required: false
    description:
    - Service endpoint mode.
      Maps docker service --endpoint-mode option.
    default: vip
    choices:
    - vip
    - dnsrr
  env:
    required: false
    default: []
    description:
    - List of the service environment variables.
      Maps docker service --env option.
  limit_cpu:
    required: false
    default: 0.000
    description:
    - Service CPU limit. 0 equals no limit.
      Maps docker service --limit-cpu option.
  reserve_cpu:
    required: false
    default: 0.000
    description:
    - Service CPU reservation. 0 equals no reservation.
      Maps docker service --reserve-cpu option.
  limit_memory:
    required: false
    default: 0
    description:
    - Service memory limit in MB. 0 equals no limit.
      Maps docker service --limit-memory option.
  reserve_memory:
    required: false
    default: 0
    description:
    - Service memory reservation in MB. 0 equals no reservation.
      Maps docker service --reserve-memory option.
  mode:
    required: false
    default: replicated
    description:
    - Service replication mode.
      Maps docker service --mode option.
  mounts:
    required: false
    description:
    - List of the service mounts. Every item must be a dictionary exposing
      the 'type', 'source' and 'dest' keys.
      Maps docker service --mount option.
    default: []
  networks:
    required: false
    default: []
    description:
    - List of the service networks names.
      Maps docker service --network option.
  publish:
    default: []
    required: false
    description:
    - List of the service published ports. Every item must be a dictionary
      exposing the 'published_port', 'target_port' and 'protocol' keys.
      Maps docker service --publish option.
  replicas:
    required: false
    default: 1
    description:
    - Number of containers instantiated in the service. Valid only if
      ``mode=='replicated'``.
      Maps docker service --replicas option.
  restart_policy:
    required: false
    default: none
    description:
    - Restart condition of the service.
      Maps docker service --restart-condition option.
    choices:
    - none
    - on-failure
    - any
  restart_policy_attempts:
    required: false
    default: 0
    description:
    - Maximum number of service restarts.
      Maps docker service --restart-max-attempts option.
  restart_policy_delay:
    required: false
    default: 0
    description:
    - Delay between restarts.
      Maps docker service --restart-delay option.
  restart_policy_window:
    required: false
    default: 0
    description:
    - Restart policy evaluation window.
      Maps docker service --restart-window option.

requirements:
  - "docker-py > https://github.com/docker/docker-py/commit/3ac73a285b2f370f6aa300d8a55c5af55660d0f4"
'''

EXAMPLES = '''
- name: define mydb service, running mysql with a volume and a published port
  swarm_service:
    name: mydb
    image: mysql:5.7
    mounts:
    - source: /swarm_data/mysql_data/
      target: /var/lib/mysql
      type: bind
    ports:
    - published_port: 3306
      target_port: 3306
      protocol: tcp
    restart_policy: any
    restart_policy_attempts: 5
    restart_policy_window: 30
- name: |
    give mysql_service access to a network named backend.
    this operation will destroy and rebuild the service as per
    https://github.com/docker/docker/issues/25876
  swarm_service:
    name: mydb
    image: mysql:5.7
    mounts:
    - source: /swarm_data/mysql_data/
      target: /var/lib/mysql
      type: bind
    networks:
    - backend
    ports:
    - published_port: 3306
      target_port: 3306
      protocol: tcp
    restart_policy: any
    restart_policy_attempts: 5
    restart_policy_window: 30
- name: change the service restart_policy
    name: mydb
    image: mysql:5.7
    mounts:
    - source: /swarm_data/mysql_data/
      target: /var/lib/mysql
      type: bind
    networks:
    - backend
    ports:
    - published_port: 3306
      target_port: 3306
      protocol: tcp
    restart_policy: on-failure
    restart_policy_attempts: 5
    restart_policy_window: 30
'''


from ansible.module_utils.basic import AnsibleModule

HAS_DOCKER=1
try:
  import docker
except ImportError:
  HAS_DOCKER=0

class DockerServiceManager:
  class DockerService:
    def __init__(self):
      self.constraints=[]
      self.image=""
      self.args = []
      self.endpoint_mode="vip"
      self.env=[]
      self.labels={}
      self.container_labels={}
      self.limit_cpu=0.000
      self.limit_memory=0
      self.reserve_cpu=0.000
      self.reserve_memory=0
      self.mode="replicated"
      self.mounts=[]
      self.constraints=[]
      self.networks=[]
      self.publish=[]
      self.replicas=1
      self.service_id=False
      self.service_version=False
      self.restart_policy = None
      self.restart_policy_attempts = None
      self.restart_policy_delay = None
      self.restart_policy_window = None

    def __str__(self):
      return str({
        'mode': self.mode,
        'env': self.env,
        'endpoint_mode': self.endpoint_mode,
        'mounts': self.mounts,
        'networks': self.networks,
        'replicas': self.replicas
      })
    def generate_docker_py_service_description(self, name, docker_networks):
        cspec={
          'Image': self.image
        }
        cspec['Mounts']=[]
        for mount_config in self.mounts:
          cspec['Mounts'].append({
            'Target': mount_config['target'],
            'Source': mount_config['source'],
            'Type': mount_config['type']
          })
        cspec['Args']=self.args
        cspec['Env']=self.env
        cspec['Labels']=self.container_labels
        restart_policy=docker.types.RestartPolicy(
          condition     = self.restart_policy,
          delay         = self.restart_policy_delay,
          max_attempts  = self.restart_policy_attempts,
          window        = self.restart_policy_window
        )
        resources={
          'Limits': {
            'NanoCPUs': int(self.limit_cpu*1000000000),
            'MemoryBytes': self.limit_memory*1024*1024
          },
          'Reservations': {
            'NanoCPUs': int(self.limit_cpu*1000000000),
            'MemoryBytes': self.limit_memory*1024*1024
          }
        }
        task_template=docker.types.TaskTemplate(
          container_spec  = cspec,
          restart_policy  = restart_policy,
          placement       = self.constraints,
          resources       = resources
        )
        mode = { 'Replicated': {'Replicas': self.replicas} }
        if self.mode=='global':
          mode = { 'Global' }

        networks=[]
        for network_name in self.networks:
          network_id = None
          try:
            network_id = filter( lambda n: n['name']==network_name, docker_networks )[0]['id']
          except:
            pass
          if network_id:
            networks.append (
              { 'Target': network_id }
            )
          else:
            raise Exception("no docker networks named: %s" % network_name)

        endpoint_spec= {'Mode': self.endpoint_mode }
        endpoint_spec['Ports'] = []
        for port in self.publish:
          endpoint_spec['Ports'].append({
            'Protocol': port['protocol'],
            'PublishedPort': port['published_port'],
            'TargetPort': port['target_port']
          })
        return task_template, networks, endpoint_spec, mode, self.labels

  def __init__(self, socket_path="/var/run/docker.sock"):
    self.dc = docker.Client()

  def get_networks_names_ids(self):
    return [{'name': n['Name'], 'id': n['Id']} for n in self.dc.networks()]

  def get_service(self, name):
    raw_data=self.dc.services( filters={'name': name} )
    if len(raw_data)==0:
      return None

    raw_data=raw_data[0]
    networks_names_ids=self.get_networks_names_ids()
    ds=DockerServiceManager.DockerService()

    task_template_data = raw_data['Spec']['TaskTemplate']

    ds.image = task_template_data['ContainerSpec']['Image']
    ds.env   = task_template_data['ContainerSpec'].get('Env',[])
    ds.args  = task_template_data['ContainerSpec'].get('Args',[])

    if 'Placement' in task_template_data.keys():
      ds.constraints = task_template_data['Placement'].get('Constraints',[])

    #ds.endpoint_mode=raw_data['Spec']['EndpointSpec']['Mode']
    raw_data_endpoint = raw_data.get('Endpoint',None)
    if raw_data_endpoint:
      raw_data_endpoint_spec = raw_data_endpoint.get('Spec',None)
      if raw_data_endpoint_spec:
        ds.endpoint_mode = raw_data_endpoint_spec.get('Mode','vip')
        for port in raw_data_endpoint_spec.get('Ports',[]):
          ds.publish.append({
            'protocol': port['Protocol'],
            'published_port': port['PublishedPort'],
            'target_port': port['TargetPort']
          })


    if 'Resources' in task_template_data.keys():
      if 'Limits' in task_template_data['Resources'].keys():
        if 'NanoCPUs' in task_template_data['Resources']['Limits'].keys():
          ds.limit_cpu      = float(task_template_data['Resources']['Limits']['NanoCPUs'])/1000000000
        if 'MemoryBytes' in task_template_data['Resources']['Limits'].keys():
          ds.limit_memory   = int(task_template_data['Resources']['Limits']['MemoryBytes'])/1024/1024
      if 'Reservations' in task_template_data['Resources'].keys():
        if 'NanoCPUs' in task_template_data['Resources']['Reservations'].keys():
          ds.reserve_cpu    = float(task_template_data['Resources']['Reservations']['NanoCPUs'])/1000000000
        if 'MemoryBytes' in task_template_data['Resources']['Reservations'].keys():
          ds.reserve_memory = int(task_template_data['Resources']['Reservations']['MemoryBytes'])/1024/1024

    ds.labels=raw_data['Spec'].get('Labels',{})
    ds.container_labels = task_template_data['ContainerSpec'].get('Labels',{})
    mode=raw_data['Spec']['Mode']
    if 'Replicated' in mode.keys():
      ds.mode=unicode('replicated','utf-8')
      ds.replicas = mode['Replicated']['Replicas']
    elif 'Global' in mode.keys():
      ds.mode='global'
    else:
      raise Exception("Unknown service mode: %s" % mode)
    for mount_data in raw_data['Spec']['TaskTemplate']['ContainerSpec'].get('Mounts',[]):
      ds.mounts.append({
        'source': mount_data['Source'],
        'type': mount_data['Type'],
        'target': mount_data['Target']
      })
    for raw_network_data in raw_data['Spec'].get('Networks',[]):
      network_name=[network_name_id['name'] for network_name_id in networks_names_ids if network_name_id['id']==raw_network_data['Target']][0]
      ds.networks.append(network_name)
    ds.service_version  = raw_data['Version']['Index']
    ds.service_id       = raw_data['ID']
    return ds

  def update_service(self, name, old_service, new_service):
    task_template, networks, endpoint_spec, mode, labels = new_service.generate_docker_py_service_description(name,self.get_networks_names_ids())
    self.dc.update_service(
      old_service.service_id,
      old_service.service_version,
      name = name,
      endpoint_config = endpoint_spec,
      networks        = networks,
      mode            = mode,
      task_template   = task_template,
      labels          = labels
    )

  def create_service(self, name, service):
    task_template, networks, endpoint_spec, mode, labels = service.generate_docker_py_service_description(name,self.get_networks_names_ids())
    self.dc.create_service(
      name            = name,
      endpoint_config = endpoint_spec,
      mode            = mode,
      networks        = networks,
      task_template   = task_template,
      labels          = labels
    )

  def remove_service(self, name):
    self.dc.remove_service(name)

  def service_from_params(self, params):
    ds                          = DockerServiceManager.DockerService()

    ds.endpoint_mode            = params['endpoint_mode']
    ds.env                      = params['env']
    ds.image                    = params['image']
    ds.mode                     = params['mode']
    ds.mounts                   = params['mounts']
    ds.networks                 = params['networks']
    ds.replicas                 = params['replicas']
    ds.restart_policy           = params['restart_policy']
    ds.restart_policy_attempts  = params['restart_policy_attempts']
    ds.restart_policy_delay     = params['restart_policy_delay']
    ds.restart_policy_window    = params['restart_policy_window']
    ds.args                     = params['args']
    ds.constraints              = params['constraints']
    ds.labels                   = params['labels']
    ds.container_labels         = params['container_labels']
    ds.limit_cpu                = params['limit_cpu']
    ds.limit_memory             = params['limit_memory']
    ds.reserve_cpu              = params['reserve_cpu']
    ds.reserve_memory           = params['reserve_memory']
    ds.publish                  = params['publish']
    return ds

  def compare_services(self, s1, s2):
    changes = []
    need_recreate = False
    if s1.endpoint_mode!=s2.endpoint_mode:
      changes.append('endpoint_mode')
    if s1.env!=s2.env:
      changes.append('env')
    if s1.mode!=s2.mode:
      changes.append('mode')
    if s1.mounts!=s2.mounts:
      changes.append('mounts')
    if s1.networks!=s2.networks:
      changes.append('networks')
      need_recreate=True
    if s1.replicas!=s2.replicas:
      changes.append('replicas')
    if s1.args!=s2.args:
      changes.append('args')
    if s1.constraints!=s2.constraints:
      changes.append('constraints')
    if s1.labels!=s2.labels:
      changes.append('labels')
    if s1.limit_cpu!=s2.limit_cpu:
      changes.append('limit_cpu')
    if s1.limit_memory!=s2.limit_memory:
      changes.append('limit_memory')
    if s1.reserve_cpu!=s2.reserve_cpu:
      changes.append('reserve_cpu')
    if s1.reserve_memory!=s2.reserve_memory:
      changes.append('reserve_memory')
    if s1.container_labels!=s2.container_labels:
      changes.append('container_labels')
    if s1.publish!=s2.publish:
      changes.append('publish')
    return len(changes)>0, changes, need_recreate

def main():
  module = AnsibleModule(
    supports_check_mode = True,
    argument_spec       = dict(
      name                    = dict( required=True ),
      image                   = dict( required=True ),
      state                   = dict( default= "present", choices=['present', 'absent'] ),
      mounts                  = dict( default=[], type='list'),
      networks                = dict( default=[], type='list'),
      args                    = dict( default=[], type='list' ),
      env                     = dict( default=[], type='list' ),
      publish                 = dict( default=[], type='list' ),
      constraints             = dict( default=[], type='list' ),
      labels                  = dict( default={}, type='dict' ),
      container_labels        = dict( default={}, type='dict' ),
      mode                    = dict( default="replicated" ),
      replicas                = dict( default=1, type='int' ),
      endpoint_mode           = dict( default='vip', choices=['vip', 'dnsrr'] ),
      restart_policy          = dict( default='none', choices=['none', 'on-failure', 'any'] ),
      limit_cpu               = dict( default=0, type='float' ),
      limit_memory            = dict( default=0, type='int' ),
      reserve_cpu             = dict( default=0, type='float' ),
      reserve_memory          = dict( default=0, type='int' ),
      restart_policy_delay    = dict( default=0, type='int' ),
      restart_policy_attempts = dict( default=0, type='int' ),
      restart_policy_window   = dict( default=0, type='int' )
    ))
  if HAS_DOCKER==0:
    module.fail_json(msg="Can't import docker module. Check requirements")

  try:
    dsm = DockerServiceManager()
  except Exception, msg:
    module.fail_json(msg = "Error instantiating docker client. Error message: %s" % msg)
  pass

  try:
    current_service = dsm.get_service(module.params['name'])
  except Exception, msg:
    module.fail_json(
      msg = "Error looking for service named %s: %s" %
                       ( module.params['name'], msg ))

  new_service = dsm.service_from_params(module.params)
  if current_service:
    if module.params['state'] == 'absent':
      if not module.check_mode:
        dsm.remove_service(module.params['name'])
      module.exit_json(msg='service removed', changed=True)
    else:
      changed, changes, need_rebuild = dsm.compare_services(current_service,new_service)
      if changed:
        if need_rebuild:
          if not module.check_mode:
            dsm.remove_service(module.params['name'])
            dsm.create_service(module.params['name'], new_service)
          module.exit_json(changed=True, msg = "rebuild service (changes: %s)" % ",".join(changes))
        else:
          if not module.check_mode:
            dsm.update_service(module.params['name'],current_service,new_service)
          module.exit_json(changed=True, msg = "service edited (changes: %s)" % ",".join(changes))
      module.exit_json(msg="service unchanged")
  else:
    if module.params['state'] == 'absent':
      module.exit_json(msg='service already absent', changed=False)
    else:
      if not module.check_mode:
        service_id=dsm.create_service( module.params['name'], new_service )
      module.exit_json(msg='service created', changed=True)

main()
