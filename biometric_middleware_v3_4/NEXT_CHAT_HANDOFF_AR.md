<div dir="rtl" align="right">

# تسليم المحادثة الجديدة — Raidat Biometric ERP / RSH

**تاريخ التحديث:** 2026-10-20  
**المشروع:** raidat  
**GitHub:** `https://github.com/RagabMahmoud1/bio_middleware`  
**فرع التطوير المعتمد:** `feature/biometric-multi-target`  
**حالة النشر:** لم تتم ترقية أي Production Runtime أو تغيير خدمة Windows؛ **Go-Live لم يحدث**.  
**الأولوية:** تجهيز ERP Test المنفصل، اختبار Middleware على بيئتي Test، ثم Preflight/Backup/Restore/Go-No-Go. المستخدم يريد الإنجاز سريعًا (نافذة مستهدفة ~ساعة وقت الطلب)، لكن **لا تُختصر شروط أمان Production**.

## 1. آخر اكتشاف على السيرفر — أهم ما تبدأ به المحادثة الجديدة

أرسل المستخدم نتيجة قراءة فعلية من السيرفر:

```text
/etc/odoo-test.conf
http_port = 8070
addons_path=/odoo16/odoo16-server/addons,/odoo16/custom/test
dbfilter = ^test_RSH$
db_name = test_RSH
max_cron_threads = 1
```

المجلدات موجودة بالفعل:

```text
/odoo16/custom/test/rgb_biometric_attendance_bridge
/odoo16/custom/test/rgb_biometric_first_last_attendance
/odoo16/custom/addons/rgb_biometric_attendance_bridge
/odoo16/custom/addons/rgb_biometric_first_last_attendance
```

**الاستنتاج:** خدمة Test الحالية على 8070 مخصصة لـ`test_RSH` و`dbfilter=^test_RSH$`؛ لا تتعامل معها كواجهة HTTP لقاعدة ERP Test (`test`) ولا تغيّر إعداداتها. أكواد الموديولات موجودة في مسار `/odoo16/custom/test` لكن SQL أظهر أنها غير مثبتة في قاعدة `test`. يجب إيجاد/إنشاء إعداد وخدمة **ERP Test منفصلين** على Port مستقل يتأكد أولًا أنه غير مستخدم، `db_name=test`, `dbfilter=^test$`، وبنفس addons path الصحيح، دون Restart أو كتابة على Live. تحقق من المنافذ والخدمات الموجودة أولًا قبل اختيار Port.

SQL المستخدم على `test`:

```text
hr_attendance             installed 16.0.2.0
rm_hr_attendance_sheet    installed 16.0.16.1
rgb_biometric_attendance_bridge        (غير ظاهر)
rgb_biometric_first_last_attendance    (غير ظاهر)
```

**أول خطوة عملية:** فحص read-only لـ `systemctl list-units --type=service --all | grep -i odoo` و`ss -lntp` وملفات config منفصلة وأذونات Odoo Test، ثم خطة تثبيت **على قاعدة test فقط**. اختبار مكان الكود، الوصول للموديولات، وحدود التأثير مهم لأن Production/Test مجلدات مجاورة وخدمة Production مشتركة لأكثر من DB.

## 2. المتطلبات المتفق عليها

- شركتان/قاعدتا Odoo16 منفصلتان: `ERP` و`RSH`. يمكن أن يعمل موظف في الشركتين؛ يُرسل الحدث لكل DB **تحتوي على Mapping لنفس Device User ID**، وليس فقط لواحدة منهما. لا تختَر شركة من الجهاز دون مصدر رسمي.
- Windows Middleware يقرأ جهاز ZKTeco `zk_room_1` وHikvision `hik_room_2`.
- Raw Events بــDevice User ID في كل DB، والتحويل إلى `hr.attendance` يوميًا للساعات المكتملة بتوقيت `Asia/Riyadh`: أول بصمة دخول وآخر بصمة خروج، إجمالي أجهزة الموظف لنفس اليوم.
- بصمة منطقية واحدة = خطأ `FIRST_LAST_SINGLE_PUNCH` للمراجعة، لا تُنشئ خروجًا وهميًا.
- تسليم مستقل لكل هدف في SQLite `event_deliveries`، لا Replay للـERP القديم؛ تعطل RSH لا يمنع ERP من التسليم، وتعطل استعلام Mapping لا يقدّم Cursor Hikvision.
- الحضور اليومي المطلوب متاح قبل 07:00 السعودية، لكن Cron المصدر عند 07:00 وتوجد مشاكل تشغيل، وتحتاج خطة ضبط/اختبار مدروسة.

## 3. ما تحقق فعليًا — لا تعيد الاختبارات دون سبب

### RSH Test: `test_RSH` — PASS
- الخدمة الحالية على `127.0.0.1:8070`؛ الموديولات `rgb_biometric_attendance_bridge` و`rgb_biometric_first_last_attendance` مثبتة، وكذلك `hr_attendance` و`rm_hr_attendance_sheet`.
- جهازان افتراضيان بسجلات `zk_room_1` و`hik_room_2`، `processing_strategy=raw_only`، وAPI Token خاص محفوظ سرًا تحت حساب `odoo16`. لا تعرض Token أو ملفات الموظفين.
- Device user exports للقراءة فقط: ZKTeco 396، Hikvision 130 حسابًا. RSH employee roster: 138. مطابقة أسماء مبدئية 51 موظفًا، 19 ZK + 46 Hik (14 موظفًا مرشحون للجهازين)، 87 يحتاجون مطابقة يدوية. **المطابقات مبدئية بالأسماء فقط وليست اعتماد هوية**.
- استيراد **65 Mapping مؤقتة** على `test_RSH` عبر سكربت مضبوط: ORM أكد Total=65، Employees=51، ZK=19، HIK=46.
- اختبار HTTP GET `allowed-employees`: Wrong Token→401، Valid Token→200/19 لـZK و200/46 لـHik، مطابق ORM.
- اختبار Events API HTTP: Wrong Token→401، invalid list→400، two identical unmapped synthetic event POSTs→200/ignored، صفر Raw Events قبل E2E.
- **اختبار E2E فعلي ناجح** بسكربت `run_rsh_test_synthetic_e2e.py` (Commit `5885049`) على `test_RSH`: موظف اصطناعي وجهازان وهميان مستقلان عن الحقيقيين، 3 events Accepted، تكرار الإرسال لا يخلق RawEvents إضافية، First/Last من 08:15 إلى 17:15 بتوقيت الرياض يخلق Attendance واحدة، بصمة منفردة `FIRST_LAST_SINGLE_PUNCH` بلا Attendance، إعادة المعالجة لا تكرر، Mapping الأصلية (19/46) unchanged. **الأحداث والأجهزة والموظف والـAttendance الاصطناعية متروكة في test_RSH** للتدقيق؛ لا تعِد السكربت لأن به حارس إعادة التشغيل.
- SQL نتائج المستخدم محفوظة بالمحادثة الماضية وبـGo-Live Checklist.

### Middleware Dev — PASS في بيئة معزولة فقط
- Middleware opt-in multi-target v3.6.0 على الفرع `feature/biometric-multi-target`.
- **103 اختبارات محلية ناجحة** عند آخر تشغيل؛ منها 4 محاكاة E2E على SQLite حقيقية مؤقتة مع Clients وأجهزة Mock: ERP-only/RSH-only/shared، الانتقال بين جهازين، عزل الفشل، استكمال Pending بعد إعادة التشغيل، حماية Cursor، منع Replay للـERP التاريخي.
- هذه ليست E2E فعلية بين نسختي Odoo Test؛ لم يُشغّل Windows Runtime الجديد. **لا تنشر على خدمة Windows الآن**.
- سكربت `scripts/bootstrap_dual_target_tests.py` مكتوب ومختبر محليًا، **لم يُنفّذ على أي Test DB**: يُنشئ أجهزة/موظفين اصطناعيين لكل قاعدة Test مع موظف مشترك، وقد يعطّل Daily First/Last Cron في Test فقط؛ راجع السياق والصلاحيات بعناية قبل التشغيل. آخر Git blob hash `557749081f9d02444259bbd7c9c6668961c67389`.

### Production — لا تغيير حتى الآن
- Windows `RaidatBiometricConnector` تعمل بإصدار ERP-only؛ ZK نحو كل 3600 ثانية، Hik نحو كل 300 ثانية. قاعدة SQLite الحالية ~4336 Event، منها 2052 synced ERP، 2284 ignored و0 pending/failed لحظة الفحص. Backup SQLite سليم Integrity فقط، **لم يختبر Restore Drill**.
- ERP Live الموديولان مثبتان، لكن Daily First/Last Cron متأخر/غير متحقق تنفيذه. RSH Live لم يجهز موديولا البصمة/Mapping. إنتاج Odoo Cron فيه مهام كثيرة متأخرة، وإعادة تشغيل الخدمة قد تنفذ مهام HR وAccounting وEDI وغيرها. **لا Restart أو تغيير Cron بدون جدول أثر وموافقة**.
- ERP and RSH Live databases منفصلتان لكن إنتاج Odoo يشترك في الخدمات/المسارات بعض الأحيان؛ لا تعدّل مجلد Addons مشترك بصورة عشوائية.

## 4. Git والملفات

المستودع المحلي لدى `rajab_work SSH MCP`:

```text
/home/ragab/odoo/odoo16/projects/bio_middleware
```

فرع Git `feature/biometric-multi-target`. آخر Commit عند إنشاء هذا الـHandoff سيتحقق عند Push؛ آخر معروف قبل تحديث الملف: `96724c2`.

أهم الملفات:

```text
biometric_middleware_v3_4/GO_LIVE_CHECKLIST_ERP_RSH_AR.md
biometric_middleware_v3_4/NEXT_CHAT_HANDOFF_AR.md
biometric_middleware_v3_4/app/multi_target.py
biometric_middleware_v3_4/app/db.py
biometric_middleware_v3_4/scripts/bootstrap_dual_target_tests.py
biometric_middleware_v3_4/scripts/run_rsh_test_synthetic_e2e.py
biometric_middleware_v3_4/tests/test_multi_target_isolated_e2e.py
```

الموديولات Odoo في مشروع محلي منفصل:

```text
/home/ragab/odoo/odoo16/projects/erp-raidatalsharq/
```

وعلى سيرفر Linux توجد نسخ في `/odoo16/custom/test` و`/odoo16/custom/addons`. يراجع `addons_path` الحقيقي لكل instance قبل Install. مسار مشروع `erp-raidatalsharq` يحتوي تعديلات أخرى غير مرتبطة (BOQ/Invoice)؛ **لا تعمل git add أو commit/push عشوائي للمشروع كله**.

## 5. الخطوات التالية — بأولوية المسار الحرج

1. **NOW / ERP Test blocker:** افحص services/ports/config والمسار الفعلي، جهز خدمة ERP Test منعزلة عن RSH Test وLive، ثبّت الموديولين على `test` فقط مع DB backup قبل Install وفحص الـCron/upgrade effect. لاحظ أن `/etc/odoo-test.conf` يقيّد HTTP إلى `test_RSH` ولا يصلح مباشرة لخدمة `test`.
2. تأكد أن ERP Test Active Company صحيحة، وثبّت API Token منفصلًا، ثم `bootstrap_dual_target_tests.py` بعد مراجعة تأثير Test Cron؛ جهز Test artifacts لنفس employee/device codes في ERP Test وRSH Test.
3. شغّل **REAL HTTP dual-target test** من isolated Linux runtime/SQLite إلى خدمتي Odoo Test المنفصلتين (لا إلى `erp.raidatalsharq.com` أو `rsh.raidatalsharq.com`). اختبر shared, ERP-only, RSH-only, idempotency, isolate outage, reboot/SQLite replay, allowlists, event ACK والـFirst/Last داخل Test.
4. اختبر Backup/Restore Drill لخدمة SQLite Windows وERP/RSH PostgreSQL backups + filestore (Restore في معزل)، وحل أو احتواء Cron overdue بالتحليل وتأمين تأثير عمليات Accounting.
5. جهز خطة تدريجية لتهيئة RSH Live (موديولات/Token/Mappings مراجعة هوية)، وخطة تشغيل v3.6 Windows بموافقة نافذة الصيانة، تحديد start_at، عدم إعادة إرسال ERP historic ACK، مسار Rollback، مراقبة دقيقة للـQueue. **قرار Go/No-Go مرهون بإغلاق الأدلة**؛ 60 دقيقة ليست تفويضًا لتجاوز شروط حماية الإنتاج.

## 6. قيود أمان وتعاون

- أي تغييرات على **Live Odoo DB، cron، Windows Middleware SQLite/config/service، production devices** ممنوعة حتى إذن المستخدم الواضح، Backup/Restore معتمد، ونافذة صيانة.
- تغييرات `test_RSH` و`test` التجريبية يوافق المستخدم على تنفيذها بعد فحص أثرها؛ لا تستنتج صلاحيات Production منها.
- لا تخزن Tokens أو CSV بها أسماء/معرّفات أفراد في Git، لا تعرضها في Chat. ملفات CSV الخاصة تحت حساب `odoo16` / `iet-rs` بصلاحية `0600`.
- أوامر Windows PowerShell ينبغي أن تكون كل واحدة في **سطر فيزيائي واحد**.
- تحديث `GO_LIVE_CHECKLIST_ERP_RSH_AR.md` بعد كل نتيجة مثبتة بالـEvidence، commit/push على feature branch فقط، ولا تدّع PASS قبل نتيجة فعلية.
- المستخدم يريد سرعة، تعليمات قصيرة، عمل فعلي بالأدوات بدل تدوير خطوات يدوية لا لزوم لها. وثّق بدقة الفرق بين Mock PASS وHTTP Test PASS وLive verified.
- بيانات Windows الخاصة، أسماء الموظفين، أرقام شخصيّة، رموز ومفاتيح API: **لا تُلصق في المحادثة أو Git**.

</div>
