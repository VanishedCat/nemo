#!/usr/bin/env python3
# coding:utf-8
from celery import Celery, Task

from instance.config import ProductionConfig

from .domainscan import DomainScan
from .fofa import Fofa
from .iplocation import IpLocation
from .portscan import PortScan
from .shodan_search import Shodan

broker = 'amqp://{}:{}@{}:{}/'.format(ProductionConfig.MQ_USERNAME,
                                      ProductionConfig.MQ_PASSWORD, ProductionConfig.MQ_HOST, ProductionConfig.MQ_PORT)
celery_app = Celery('nemo', broker=broker, backend='rpc://')

TASK_ACTION = {
    'portscan':   PortScan().run,
    'iplocation':   IpLocation().run,
    'fofasearch':   Fofa().run,
    'shodansearch':   Shodan().run,
    'domainscan':   DomainScan().run,
}

class UpdateTaskStatus(Task):
    '''在celery的任务异步完成时，显示完成状态和结果
    '''

    def on_success(self, retval, task_id, args, kwargs):
        print('task {} done: {}'.format(task_id, retval))
        return super(UpdateTaskStatus, self).on_success(retval, task_id, args, kwargs)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        print('task {} fail, reason: {}'.format(task_id, exc))
        return super(UpdateTaskStatus, self).on_failure(exc, task_id, args, kwargs, einfo)

def new_task(action, options):
    '''开始一个任务
    '''
    if action in TASK_ACTION:
        task_run = TASK_ACTION.get(action)
        result = task_run(options)
        return result
    else:
        return {'status': 'fail', 'msg': 'no task'}


@celery_app.task(base=UpdateTaskStatus)
def portscan(options):
    '''端口扫描综合任务
    '''
    return new_task('portscan', options)


@celery_app.task(base=UpdateTaskStatus)
def fofasearch(options):
    '''调用fofa API
    '''
    return new_task('fofasearch', options)

@celery_app.task(base=UpdateTaskStatus)
def shodansearch(options):
    '''调用shodan API
    '''
    return new_task('shodansearch', options)

@celery_app.task(base=UpdateTaskStatus)
def domainscan(options):
    '''域名收集综合信息
    '''
    return new_task('domainscan', options)

@celery_app.task(base=UpdateTaskStatus)
def iplocation(options):
    '''IP归属地
    '''
    return new_task('iplocation', options)


@celery_app.task(base=UpdateTaskStatus)
def domainscan_with_portscan(options):
    '''域名收集综合信息
    '''
    domainscan = DomainScan()
    portscan = PortScan()
    # 域名任务
    domainscan.prepare(options)
    domain_list = domainscan.execute()
    result  =  domainscan.save_domain(domain_list)
    # 得到域名的IP及C段
    ip_set = set()
    for domain in domain_list:
        if 'A' in domain and domain['A']:
            for ip in domain['A']:
                if options['networkscan']:
                    network = ip.split('.')[0:3]
                    network.append('0/24')
                    ip_set.update(['.'.join(network)])
                else:
                    ip_set.update(domain['A'])
    # 生成portscan的默认参数
    options_portscan = {'target': list(ip_set), 'iplocation':True,'webtitle': options['webtitle'],
                        'whatweb':options['whatweb'], 'org_id': None if 'org_id' not in options else options['org_id']}
    # 执行portscan任务
    result.update(portscan.run(options_portscan))

    return result
