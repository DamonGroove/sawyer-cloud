<?php
declare(strict_types=1);

/**
 * customization/apps/branding-default/lib/AppInfo/Application.php
 *
 * Minimum Nextcloud app skeleton. Registers the JS and CSS shipped in this
 * app so they are loaded on every page.
 *
 * CLAUDE.md §3.4: this PHP file is OVERRIDE territory — operators only
 * touch js/ and css/. Changes here go through an engineering PR.
 */

namespace OCA\BrandingDefault\AppInfo;

use OCP\AppFramework\App;
use OCP\AppFramework\Bootstrap\IBootContext;
use OCP\AppFramework\Bootstrap\IBootstrap;
use OCP\AppFramework\Bootstrap\IRegistrationContext;
use OCP\Util;

class Application extends App implements IBootstrap {
    public const APP_ID = 'branding_default';

    public function __construct() {
        parent::__construct(self::APP_ID);
    }

    /**
     * No services to register in the container — this app is presentation-only.
     */
    public function register(IRegistrationContext $context): void {
        // intentionally empty
    }

    /**
     * Inject our script + stylesheet on every request. `Util::addScript`
     * honors Nextcloud's CSP nonce machinery, so inline handlers remain
     * forbidden (CLAUDE.md §3.4 reminder) but our bundled file runs.
     */
    public function boot(IBootContext $context): void {
        Util::addScript(self::APP_ID, 'main');
        Util::addStyle(self::APP_ID, 'main');
    }
}
