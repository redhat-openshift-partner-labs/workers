#! /usr/bin/env bash

# get the current pull secret
oc extract secret/pull-secret -n openshift-config --to=.

# remove the cloud.openshift.com auth
jq -c 'del(.auths["cloud.openshift.com"])' .dockerconfigjson > disable-insights.json

# update the pull secret .dockerconfigjson to disable insights
oc set data secret/pull-secret -n openshift-config --from-file=.dockerconfigjson=disable-insights.json