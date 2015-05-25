# coding: utf8
import time

from .utils import get_sorted_data


"""
Node 负责存储 ；Transation 负责调用Node
"""

NodeClasses = []


class NodeMeta(type):
    def __init__(cls, name, bases, dct):
        type.__init__(cls, name, bases, dct)
        NodeClasses.append(cls)


class TransactionNode(object):
    """
    一次函数调用只使用一次start , stop
    对于异步函数，start , stop 之间有多次resume, 和 hangup
    """
    __metaclass__ = NodeMeta

    result = {}
    flat_result = {}

    def __init__(self, name):
        self.count = 0
        self.running = False
        self.time = 0
        self.name = name
        self.children = {}
        self.start_time = 0
        # is_start 用于标记上是否已经调用了start
        self.is_start = False

    def start(self):
        """
        函数首次启动
        """
        self.running = True
        self.count += 1
        self.start_time = time.time()
        self.is_start = True

    def restart(self):
        """
        重启， 重置启动时间, 用于Task的callback
        """
        self.running = True
        self.start_time = time.time()
        self.is_start = True

    def stop(self):
        """
        关闭
        """
        self.running = False
        self.time += (time.time() - float(self.start_time))
        self.is_start = False

    def resume(self):
        """
        用于Runner.run, 统计异步执行
        """
        if self.is_start:
            return
        self.running = True
        self.start_time = time.time()

    def hang_up(self):
        """
        用于Runner.run, 统计异步执行
        """
        if self.is_start:
            return
        self.running = False
        self.time += (time.time() - float(self.start_time))

    def is_running(self):
        return self.running

    def classify(self):
        """
        子类进行特殊话处理
        """
        pass

    @classmethod
    def get_result(cls):
        return cls.result, cls.flat_result

    @classmethod
    def trim_data(cls):
        """
        渲染或者存储之前整理数据
        """
        cls.result = cls._sort_result(Transaction.root.children)
        cls.flat_result = get_sorted_data(cls.flat_result)

    @classmethod
    def _sort_result(cls, children_nodes):
        funcs_list = []
        for name, node in children_nodes.items():
            if node.is_running():
                node.stop()
            node.classify() # node 分类处理
            # construtct flat result
            flat_data = cls.flat_result.get(name, {"count": 0, 'time': 0})
            flat_data['count'] += node.count
            flat_data['time'] += node.time
            cls.flat_result[name] = flat_data

            node.time = round(node.time*1000, 2)

            funcs_list.append({'name': name, 'count': node.count, 'time': node.time, 'children': node.children})
        funcs_list = sorted(funcs_list, key=lambda x: x['time'], reverse=True)

        for item in funcs_list:
            item['children'] = cls._sort_result(item['children'])

        return funcs_list

    @staticmethod
    def clear():
        TransactionNode.result = {}
        TransactionNode.flat_result = {}


class Transaction(object):

    current = root = TransactionNode('root')  # Transaction.root始终是单例

    active = True  # 标记当前的统计是否有效

    @classmethod
    def _clear(cls):
        cls.root.children = {}
        cls.current = cls.root

    @classmethod
    def start(cls):
        cls.active = True
        cls._clear()

    @classmethod
    def stop(cls):
        cls.active = False
        cls._clear()

    @classmethod
    def get_current(cls):
        return cls.current

    @classmethod
    def set_current(cls, transaction):
        cls.current = transaction


class SyncTransactionContext(object):

    node_cls = TransactionNode

    def __init__(self, full_name):
        self.full_name = full_name
        self.transaction = None

    def __enter__(self):
        if Transaction.active:
            self.parent = Transaction.current
            self.transaction = self.parent.children.get(self.full_name, self.node_cls(self.full_name))
            self.transaction.start()
            self.parent.children[self.full_name] = self.transaction
            Transaction.set_current(self.transaction)
            return self.transaction

    def __exit__(self, exc, value, tb):
        if Transaction.active:
            self.transaction.stop()
            Transaction.set_current(self.parent)


class AsyncTransactionContext(object):
    """
    装饰Runner.run时使用
    """
    def __init__(self, transaction):
        self.transaction = transaction

    def __enter__(self):
        if Transaction.active:
            self.parent = Transaction.current
            Transaction.set_current(self.transaction)
            self.transaction.resume()
            return self

    def __exit__(self, exc, value, tb):
        if Transaction.active:
            self.transaction.hang_up()
            Transaction.set_current(self.parent)


class AsyncCallbackContext(object):
    """
    gen.Task 执行callback时， 实际是进入了关联的Runner的run方法， 这部分代码执行时间不作为Task的时间
    """
    def __enter__(self):
        if Transaction.active:
            Transaction.current.stop()
            self.parent = Transaction.current
            return self

    def __exit__(self, exc, value, tb):
        if Transaction.active:
            self.parent.restart()
            Transaction.set_current(self.parent)

"""
Runner __init__ 时附加属性_td_transaction

Runner.run
   tempt_parent = Transaction.current
   Transaction.set_current(_td_transaction)
   _td_transaction.resume()
   run
   _td_transaction.hang_up()
   Transaction.set_current(tempt_parent)
"""
