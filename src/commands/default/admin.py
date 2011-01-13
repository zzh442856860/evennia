"""

Admin commands

"""

from django.conf import settings
from django.contrib.auth.models import User
from src.players.models import PlayerDB
from src.server.sessionhandler import SESSIONS
from src.permissions.permissions import has_perm, has_perm_string
from src.permissions.models import PermissionGroup
from src.utils import utils
from src.commands.default.muxcommand import MuxCommand

class CmdBoot(MuxCommand):
    """
    @boot 

    Usage
      @boot[/switches] <player obj> [: reason]

    Switches:
      quiet - Silently boot without informing player
      port - boot by port number instead of name or dbref
      
    Boot a player object from the server. If a reason is
    supplied it will be echoed to the user unless /quiet is set. 
    """
    
    key = "@boot"
    permissions = "cmd:boot"
    help_category = "Admin"

    def func(self):
        "Implementing the function"
        caller = self.caller
        args = self.args
        
        if not args:
            caller.msg("Usage: @boot[/switches] <player> [:reason]")
            return

        if ':' in args:
            args, reason = [a.strip() for a in args.split(':', 1)]
        boot_list = []
        reason = ""

        if 'port' in self.switches:
            # Boot a particular port.
            sessions = SESSIONS.get_session_list(True)
            for sess in sessions:
                # Find the session with the matching port number.
                if sess.getClientAddress()[1] == int(args):
                    boot_list.append(sess)
                    break
        else:
            # Boot by player object
            pobj = caller.search("*%s" % args, global_search=True)
            if not pobj:
                return            
            if pobj.character.has_player:
                if not has_perm(caller, pobj, 'can_boot'):
                    string = "You don't have the permission to boot %s."
                    pobj.msg(string)
                    return 
                # we have a bootable object with a connected user
                matches = SESSIONS.sessions_from_player(pobj)
                for match in matches:
                    boot_list.append(match)
            else:
                caller.msg("That object has no connected player.")
                return

        if not boot_list:
            caller.msg("No matches found.")
            return

        # Carry out the booting of the sessions in the boot list.

        feedback = None 
        if not 'quiet' in self.switches:
            feedback = "You have been disconnected by %s.\n" % caller.name
            if reason:
                feedback += "\nReason given: %s" % reason

        for session in boot_list:
            name = session.name
            session.msg(feedback)
            session.disconnect()
            caller.msg("You booted %s." % name)


class CmdDelPlayer(MuxCommand):
    """
    delplayer - delete player from server

    Usage:
      @delplayer[/switch] <name> [: reason]
      
    Switch:
      delobj - also delete the player's currently
                assigned in-game object.   

    Completely deletes a user from the server database,
    making their nick and e-mail again available.    
    """

    key = "@delplayer"
    permissions = "cmd:delplayer"
    help_category = "Admin"

    def func(self):
        "Implements the command."

        caller = self.caller
        args = self.args 

        if not args:
            caller.msg("Usage: @delplayer[/delobj] <player/user name or #id> [: reason]")
            return

        reason = ""
        if ':' in args:
            args, reason = [arg.strip() for arg in args.split(':', 1)]

        # We use player_search since we want to be sure to find also players
        # that lack characters.
        players = caller.search("*%s" % args)
        if not players:
            try:
                players = PlayerDB.objects.filter(id=args)
            except ValueError:
                pass

        if not players:            
            # try to find a user instead of a Player
            try:
                user = User.objects.get(id=args)
            except Exception:            
                try:
                    user = User.objects.get(username__iexact=args)                        
                except Exception:
                    string = "No Player nor User found matching '%s'." % args
                    caller.msg(string)
                    return                     
            try:
                player = user.get_profile()
            except Exception:
                player = None 
                                
            if not has_perm_string(caller, 'manage_players'):
                string = "You don't have the permissions to delete this player."
                caller.msg(string)
                return 

            string = ""
            name = user.username
            user.delete()
            if player:
                name = player.name
                player.delete()
                string = "Player %s was deleted." % name
            else:
                string += "The User %s was deleted. It had no Player associated with it." % name
            caller.msg(string)
            return 
    
        elif len(players) > 1:
            string = "There where multiple matches:"
            for player in players:
                string += "\n %s %s" % (player.id, player.key) 
            return 

        else:
            # one single match

            player = players[0]
            user = player.user
            character = player.character

            if not has_perm(caller, player, 'manage_players'):
                string = "You don't have the permissions to delete that player."
                caller.msg(string)
                return 

            uname = user.username
            # boot the player then delete 
            if character and character.has_player:
                caller.msg("Booting and informing player ...")
                string = "\nYour account '%s' is being *permanently* deleted.\n" %  uname
                if reason:
                    string += " Reason given:\n  '%s'" % reason
                character.msg(string)
                caller.execute_cmd("@boot %s" % uname)
                
            player.delete()
            user.delete()    
            caller.msg("Player %s was successfully deleted." % uname)


class CmdEmit(MuxCommand):                    
    """
    @emit

    Usage:
      @emit[/switches] [<obj>, <obj>, ... =] <message>
      @remit           [<obj>, <obj>, ... =] <message> 
      @pemit           [<obj>, <obj>, ... =] <message> 

    Switches:
      room : limit emits to rooms only 
      players : limit emits to players only 
      contents : send to the contents of matched objects too
      
    Emits a message to the selected objects or to
    your immediate surroundings. If the object is a room,
    send to its contents. @remit and @pemit are just 
    limited forms of @emit, for sending to rooms and 
    to players respectively.
    """
    key = "@emit"
    aliases = ["@pemit", "@remit"]
    permissions = "cmd:emit"
    help_category = "Admin"

    def func(self):
        "Implement the command"
        
        caller = self.caller
        args = self.args

        if not args:
            string = "Usage: "
            string += "\n@emit[/switches] [<obj>, <obj>, ... =] <message>"
            string += "\n@remit           [<obj>, <obj>, ... =] <message>"
            string += "\n@pemit           [<obj>, <obj>, ... =] <message>"
            caller.msg(string)
            return 

        rooms_only = 'rooms' in self.switches
        players_only = 'players' in self.switches
        send_to_contents = 'contents' in self.switches
        
        # we check which command was used to force the switches
        if self.cmdstring == '@remit':
            rooms_only = True
        elif self.cmdstring == '@pemit':
            players_only = True

        if not self.rhs:
            message = self.args
            objnames = [caller.location.key]
        else:
            message = self.rhs
            objnames = self.lhslist
            
        # send to all objects
        for objname in objnames:
            obj = caller.search(objname, global_search=True)
            if not obj:
                return 
            if rooms_only and not obj.location == None:
                caller.msg("%s is not a room. Ignored." % objname)
                continue
            if players_only and not obj.has_player:
                caller.msg("%s has no active player. Ignored." % objname)
                continue
            if has_perm(caller, obj, 'send_to'):
                obj.msg(message)
                if send_to_contents:
                    for content in obj.contents:
                        content.msg(message)
                    caller.msg("Emitted to %s and its contents." % objname)
                else:
                    caller.msg("Emitted to %s." % objname)
            else:
                caller.msg("You are not allowed to send to %s." % objname)



class CmdNewPassword(MuxCommand):
    """
    @setpassword

    Usage:
      @userpassword <user obj> = <new password>

    Set a player's password.
    """
    
    key = "@userpassword"
    permissions = "cmd:newpassword"
    help_category = "Admin"

    def func(self):
        "Implement the function."

        caller = self.caller

        if not self.rhs:
            caller.msg("Usage: @userpassword <user obj> = <new password>")
            return 
        
        # the player search also matches 'me' etc. 
        character = caller.search("*%s" % self.lhs, global_search=True)            
        if not character:
            return     
        player = character.player
        player.user.set_password(self.rhs)
        player.user.save()
        caller.msg("%s - new password set to '%s'." % (player.name, self.rhs))
        if character != caller:
            player.msg("%s has changed your password to '%s'." % (caller.name, self.rhs))


class CmdPerm(MuxCommand):
    """
    @perm - set permissions

    Usage:
      @perm[/switch] [<object>] = [<permission>]
      @perm[/switch] [*<player>] = [<permission>]

    Switches:
      del : delete the given permission from <object>.
      list : list all permissions, or those set on <object>
            
    Use * before the search string to add permissions to a player. 
    This command sets/clears individual permission strings on an object.
    Use /list without any arguments to see all available permissions
    or those defined on the <object>/<player> argument. 
    """
    key = "@perm"
    aliases = "@setperm"
    permissions = "cmd:perm"
    help_category = "Admin"

    def func(self):
        "Implement function"

        caller = self.caller
        switches = self.switches
        lhs, rhs = self.lhs, self.rhs

        if not self.args:
            
            if "list" not in switches:
                string = "Usage: @setperm[/switch] [object = permission]\n" 
                string += "       @setperm[/switch] [*player = permission]"
                caller.msg(string)
                return
            else:
                #just print all available permissions
                string = "\nAll defined permission groups and keys (i.e. not locks):"
                pgroups = list(PermissionGroup.objects.all())
                pgroups.sort(lambda x, y: cmp(x.key, y.key)) # sort by group key

                for pgroup in pgroups:
                    string += "\n\n - {w%s{n (%s):" % (pgroup.key, pgroup.desc)
                    string += "\n%s" % \
                        utils.fill(", ".join(sorted(pgroup.group_permissions)))                
                caller.msg(string)
                return 

        # locate the object/player         
        obj = caller.search(lhs, global_search=True)
        if not obj:
            return         
        
        pstring = ""
        if utils.inherits_from(obj, settings.BASE_PLAYER_TYPECLASS):
            pstring = " Player "
        
        if not rhs: 
            string = "Permission string on %s{w%s{n: " % (pstring, obj.key)
            if not obj.permissions:
                string += "<None>"
            else:
                string += ", ".join(obj.permissions)
            if pstring and obj.is_superuser:
                string += "\n(... But this player is a SUPERUSER! "
                string += "All access checked are passed automatically.)"
            elif obj.player and obj.player.is_superuser:
                string += "\n(... But this object's player is a SUPERUSER! "
                string += "All access checked are passed automatically.)"
            caller.msg(string)
            return 
            
        # we supplied an argument on the form obj = perm

        cstring = ""
        tstring = ""
        if 'del' in switches:
            # delete the given permission(s) from object.
            for perm in self.rhslist:
                try:
                    index = obj.permissions.index(perm)
                except ValueError:
                    cstring += "\nPermission '%s' was not defined on %s%s." % (perm, pstring, lhs)
                    continue
                permissions = obj.permissions
                del permissions[index]
                obj.permissions = permissions 
                cstring += "\nPermission '%s' was removed from %s%s." % (perm, pstring, obj.name)
                tstring += "\n%s revokes the permission '%s' from you." % (caller.name, perm)
        else:
            # As an extra check, we warn the user if they customize the 
            # permission string (which is okay, and is used by the lock system)            
            permissions = obj.permissions
            for perm in self.rhslist:

                if perm in permissions:
                    cstring += "\nPermission '%s' is already defined on %s%s." % (rhs, pstring, obj.name)
                else:
                    permissions.append(perm)
                    obj.permissions = permissions
                    cstring += "\nPermission '%s' given to %s%s." % (rhs, pstring, obj.name)
                    tstring += "\n%s granted you the permission '%s'." % (caller.name, rhs)        
        caller.msg(cstring.strip())
        if tstring:
            obj.msg(tstring.strip())


class CmdPuppet(MuxCommand):
    """
    Switch control to an object
    
    Usage:
      @puppet <character object>
      
    This will attempt to "become" a different character. Note that this command does not check so that
    the target object has the appropriate cmdset. You cannot puppet a character that is already "taken".
    """

    key = "@puppet"
    permissions = "cmd:puppet"
    help_category = "Admin"

    def func(self):
        """
        Simple puppet method (does not check permissions)
        """
        caller = self.caller
        if not self.args:
            caller.msg("Usage: @puppet <character>")
            return 

        player = caller.player
        new_character = caller.search(self.args)
        if not new_character:
            return 
        if not utils.inherits_from(new_character, settings.BASE_CHARACTER_TYPECLASS):
            caller.msg("%s is not a Character." % self.args)
            return
        if player.swap_character(new_character):
            new_character.msg("You now control %s." % new_character.name)
        else:
            caller.msg("You cannot control %s." % new_character.name)

class CmdWall(MuxCommand):
    """
    @wall

    Usage:
      @wall <message>
      
    Announces a message to all connected players.
    """
    key = "@wall"
    permissions = "cmd:wall"
    help_category = "Admin"

    def func(self):
        "Implements command"
        if not self.args:
            self.caller.msg("Usage: @wall <message>")
            return
        message = "%s shouts \"%s\"" % (self.caller.name, self.args)
        SESSIONS.announce_all(message)