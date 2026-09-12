"""Disabled example; rename without underscore to enable. Does not modify gameplay."""
import logging
log=logging.getLogger('nxt.extension.audit')
def register(world):
 world.hook('login',lambda world,player:log.info('Extension observed trainer login: %s',player.username))
 world.hook('trade_complete',lambda world,trade:log.info('Extension observed committed trade: %s',trade['id']))
