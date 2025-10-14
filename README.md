# Network automation example repository

This repository is to serve as general guide on how to automate a modern network.

## Goals

- Easy to reason about
- Easy to maintain
- Ability for network engineers, not just software engineers to work with

## Directory structure

```tree
.
├── acls                # This is where aerleon works from
│   ├── def             # 
│   └── policies
│       └── pol
├── data                # Your data that will be used for templates
├── generated           # Finished products
│   ├── acl
│   ├── data
│   ├── full_configs
│   └── push
├── templates
│   ├── ios
│   └── junos
```

## Features

- `JSON` based data system
- `ACL` generation and automation using `Aerleon`
- Device configuration using `Jinja` templates
- Data validators using Python
- Multi-system data for templates using Python
- Ability to slow roll configuration coverage

## Workflow

### Add a new device

### Generate ACLs

### Add a new field

## Tools

| Tool | URL | Used for |
|---|---|---|
| aerleon | [Github](https://github.com/aerleon/aerleon) | `ACL` generation |
| minijinja | [Github](https://github.com/mitsuhiko/minijinja) | Render device templates |
| cfgcut | [Github](https://github.com/bedecarroll/cfgcut) | Get only parts of configurations for pushes |
| mise | [Github](https://github.com/jdx/mise) | Environment setup and task runner |

## Limitations

This repo does not represent a full end to end automation platform. Ideally
a lot of the components in this repo would not happen through CI but with
proper systems that are more tightly coupled.

### Cardinality

You will need a system to provide a semaphore for each device. This will allow
you to ensure you don't push to 1,000 devices at the same time and cause an
outage. Generally a system like this has a way to "slice" the network.
Typically this is via site and device role. You will then be able to write
rules like:

```yaml
# Concurrent limits by role
global:
  dgw: 100
  wgw: 10

# Further limits by site
site:
  dgw: 10
  wgw: 1
```

These rules can be read as, devices with a role of `dgw` can do 100 operations
in the network but if you have 50 `dgw` devices in a single site only 10 can be
operated on at once. Ideally you would extend this even further to enable
`anti-affinity` rules so `HSRP` pairs cannot be operated on at once.

### Monitoring

Typically outside of the purview of device management but none the less important.
